"""Photo path utils
    Extract filename and extension from photo.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)

    Returns:
        Tuple of (name, extension) where name is filename without extension
        and extension is the file extension.

This module contains utilities for generating photo file paths and managing
file naming conventions for photo synchronization.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"

import base64
import os
import re
import unicodedata
from urllib.parse import unquote

from src import get_logger

LOGGER = get_logger()

# ``${photo.*}`` tokens for photos.file_format; unknown tokens are left literal.
_TEMPLATE_TOKEN_RE = re.compile(r"\$\{([^}]+)\}")


def get_photo_name_and_extension(photo, file_size: str) -> tuple[str, str]:
    """Extract filename and extension from photo.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)

    Returns:
        Tuple of (name, extension) where name is filename without extension
        and extension is the file extension
    """
    # Decode URL-encoded filename from iCloud API
    # This handles special characters like %CC%88 (combining diacritical marks)
    filename = unquote(photo.filename)
    name, extension = filename.rsplit(".", 1) if "." in filename else [filename, ""]

    # Handle original_alt file type mapping
    if file_size == "original_alt" and file_size in photo.versions:
        filetype = photo.versions[file_size]["type"]
        if filetype in _get_original_alt_filetype_mapping():
            extension = _get_original_alt_filetype_mapping()[filetype]
        else:
            LOGGER.warning(
                f"Unknown filetype {filetype} for original_alt version of {filename}",
            )

    return name, extension


# Module-level default filename format. ``sync_photos`` sets this once at
# the start of a sync run via ``set_default_filename_format`` so the value
# threads through ``generate_photo_path`` -> ``collect_download_task`` without
# requiring a config argument on every downstream signature.
_DEFAULT_FILENAME_FORMAT = "metadata"


def set_default_filename_format(filename_format: str) -> None:
    """Set the module-level default filename format. See get_photos_filename_format."""
    global _DEFAULT_FILENAME_FORMAT
    if filename_format in ("metadata", "simple"):
        _DEFAULT_FILENAME_FORMAT = filename_format


def get_default_filename_format() -> str:
    """Read the current module-level default filename format.

    Public accessor so callers in other modules can observe live updates
    from ``set_default_filename_format`` without reaching into the
    underscore-prefixed module global (which violates SLF001).
    """
    return _DEFAULT_FILENAME_FORMAT


# photos.file_format: a single template applied to EVERY downloaded version
# (mirrors folder_format). None means "no template; use filename_format".
_FILE_FORMAT: str | None = None
_VARIANT_SEPARATOR = "_"
# Versions that are the "primary" copy and get no variant tag in ${photo.variant*}.
_PRIMARY_VERSIONS = frozenset({"original", "full"})


def set_file_format(template: str | None, variant_separator: str = "_") -> None:
    """Set the single filename template + variant separator (photos.file_format)."""
    global _FILE_FORMAT, _VARIANT_SEPARATOR
    _FILE_FORMAT = template or None
    _VARIANT_SEPARATOR = variant_separator if variant_separator is not None else "_"


def get_file_format() -> str | None:
    """Read the single filename template (public accessor; avoids SLF001)."""
    return _FILE_FORMAT


def render_filename_template(template: str, photo, file_size: str) -> str:
    """Render photos.file_format for one photo version.

    Tokens (unknown ones left literal): ``${photo.filename}`` ``${photo.ext}``
    ``${photo.id}`` (base64url asset id) ``${photo.file_size}`` and the
    created-date parts ``${photo.year}`` ``${photo.month}`` ``${photo.day}``.

    Variant tokens are empty for the primary versions (original/full) and the
    version name otherwise: ``${photo.variant}`` (bare, e.g. ``medium``) and
    ``${photo.variant_suffix}`` (separator + variant, e.g. ``_medium``) so the
    separator only appears when there actually is a variant.
    """
    name, extension = get_photo_name_and_extension(photo, file_size)
    created = getattr(photo, "created", None)
    is_primary = file_size in _PRIMARY_VERSIONS
    variant = "" if is_primary else file_size
    variant_suffix = "" if is_primary else f"{_VARIANT_SEPARATOR}{file_size}"
    values = {
        "photo.filename": name,
        "photo.ext": extension,
        "photo.id": base64.urlsafe_b64encode(photo.id.encode()).decode(),
        "photo.file_size": file_size,
        "photo.variant": variant,
        "photo.variant_suffix": variant_suffix,
        "photo.year": f"{created.year:04d}" if created else "",
        "photo.month": f"{created.month:02d}" if created else "",
        "photo.day": f"{created.day:02d}" if created else "",
    }

    def _sub(match: re.Match) -> str:
        token = match.group(1).strip()
        replacement = values.get(token)
        return replacement if replacement is not None else match.group(0)

    return _TEMPLATE_TOKEN_RE.sub(_sub, template)


def generate_photo_filename_with_metadata(
    photo, file_size: str, filename_format: str | None = None,
) -> str:
    """Generate filename for a photo asset.

    Two conventions supported (controlled by ``filename_format`` or the
    module-level default set by ``set_default_filename_format``):

    - ``"metadata"`` (default): ``name__filesize__base64id.extension`` —
      mandarons' historical format, encodes CloudKit asset id into the filename.
    - ``"simple"``: ``name.extension`` — boredazfcuk/Apple convention. Lets
      users migrate from boredazfcuk-format trees without re-downloading.
      ``collect_download_task`` detects collisions and falls back to the
      metadata-suffix path for the colliding photo so both files coexist.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)
        filename_format: ``"metadata"`` or ``"simple"``, or ``None`` to
            use the module-level default.

    Returns:
        Filename string in the chosen format.
    """
    forced = filename_format  # explicit value; None means a normal (non-fallback) call
    if filename_format is None:
        filename_format = _DEFAULT_FILENAME_FORMAT
    name, extension = get_photo_name_and_extension(photo, file_size)

    # photos.file_format wins for normal calls; the collision fallback passes
    # filename_format="metadata" explicitly to force the always-unique name.
    if forced != "metadata" and _FILE_FORMAT is not None:
        rendered = render_filename_template(_FILE_FORMAT, photo, file_size)
        if rendered.strip():
            return rendered
        # Defensive: a template that renders empty for this version (e.g. a bare
        # ${photo.variant} on an original) would otherwise yield a path pointing
        # at the directory. Fall back to filename_format instead.
        LOGGER.warning(
            f"photos.file_format rendered an empty name for {file_size}; "
            f"falling back to {filename_format} naming.",
        )

    if filename_format == "simple":
        return name if extension == "" else f"{name}.{extension}"

    photo_id_encoded = base64.urlsafe_b64encode(photo.id.encode()).decode()
    if extension == "":
        return f"{'__'.join([name, file_size, photo_id_encoded])}"
    else:
        return f"{'__'.join([name, file_size, photo_id_encoded])}.{extension}"


def create_folder_path_if_needed(
    destination_path: str, folder_format: str | None, photo,
) -> str:
    """Create folder path based on folder format and photo creation date.

    Args:
        destination_path: Base destination path
        folder_format: strftime format string for folder creation (e.g., "%Y/%m")
        photo: Photo object with created date

    Returns:
        Full destination path including created folder if folder_format is specified
    """
    if folder_format is None:
        return destination_path

    folder = photo.created.strftime(folder_format)
    full_destination = os.path.join(destination_path, folder)
    os.makedirs(full_destination, exist_ok=True)
    return full_destination


def normalize_file_path(file_path: str) -> str:
    """Normalize file path using Unicode NFC normalization.

    Args:
        file_path: File path to normalize

    Returns:
        Normalized file path
    """
    return unicodedata.normalize("NFC", file_path)


def rename_legacy_file_if_exists(old_path: str, new_path: str) -> None:
    """Rename legacy file format to new format if it exists.

    Args:
        old_path: Path to legacy file format
        new_path: Path to new file format
    """
    import os

    if os.path.isfile(old_path):
        os.rename(old_path, new_path)


def _get_original_alt_filetype_mapping() -> dict:
    """Get mapping of original_alt file types to extensions.

    Returns:
        Dictionary mapping file types to extensions
    """
    return {
        "public.png": "png",
        "public.jpeg": "jpeg",
        "public.heic": "heic",
        "public.image": "HEIC",
        "com.sony.arw-raw-image": "arw",
        "org.webmproject.webp": "webp",
        "com.compuserve.gif": "gif",
        "com.adobe.raw-image": "dng",
        "public.tiff": "tiff",
        "public.jpeg-2000": "jp2",
        "com.truevision.tga-image": "tga",
        "com.sgi.sgi-image": "sgi",
        "com.adobe.photoshop-image": "psd",
        "public.pbm": "pbm",
        "public.heif": "heif",
        "com.microsoft.bmp": "bmp",
        "com.fuji.raw-image": "raf",
        "com.canon.cr2-raw-image": "cr2",
        "com.panasonic.rw2-raw-image": "rw2",
        "com.nikon.nrw-raw-image": "nrw",
        "com.pentax.raw-image": "pef",
        "com.nikon.raw-image": "nef",
        "com.olympus.raw-image": "orf",
        "com.adobe.pdf": "pdf",
        "com.canon.cr3-raw-image": "cr3",
        "com.olympus.or-raw-image": "orf",
        "public.mpo-image": "mpo",
        "com.dji.mimo.pano.jpeg": "jpg",
        "public.avif": "avif",
        "com.canon.crw-raw-image": "crw",
    }
