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

# The Live Photo paired-video file_size variants. These are QuickTime movies,
# not images, even though the parent asset's filename ends in .HEIC/.JPG.
_LIVE_VIDEO_SIZES = frozenset({"live_video_original", "live_video_medium", "live_video_thumb"})


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

    # Handle Live Photo paired-video versions. photo.filename is the STILL
    # (e.g. IMG_1234.HEIC), but the live_video_* versions are the QuickTime
    # movie half of the Live Photo. Without this the .mov is written with the
    # still's extension (IMG_1234__live_video_original__<id>.HEIC), which every
    # downstream image tool then rejects as "unsupported image format" because
    # it is really a video. Map to the real container extension instead.
    elif file_size in _LIVE_VIDEO_SIZES and file_size in photo.versions:
        filetype = photo.versions[file_size].get("type")
        extension = _get_video_filetype_mapping().get(filetype, "MOV")

    return name, extension


# Module-level toggle for hiding untouched originals of edited photos via
# the ``.original.bak`` suffix convention. ``sync_photos`` sets this once
# per sync run from ``photos.preserve_originals_as_bak``.
_PRESERVE_ORIGINALS_AS_BAK = False


def set_preserve_originals_as_bak(value: bool) -> None:
    """Set the module-level toggle for hiding untouched originals via .original.bak."""
    global _PRESERVE_ORIGINALS_AS_BAK
    _PRESERVE_ORIGINALS_AS_BAK = bool(value)


def _photo_has_alt_version(photo) -> bool:
    """Check whether the asset has an edited (``original_alt``) version on iCloud.

    Soft check — exceptions reading ``photo.versions`` are treated as "no alt"
    so a partial CloudKit record cannot break the filename pipeline.
    """
    try:
        return "original_alt" in photo.versions
    except Exception:
        return False


_TEMPLATE_TOKEN_RE = re.compile(r"\$\{([^}]+)\}")
_DEFAULT_FILENAME_FORMAT = "metadata"


def set_default_filename_format(filename_format: str) -> None:
    """Set the module-level default filename format. See get_photos_filename_format."""
    global _DEFAULT_FILENAME_FORMAT
    if filename_format in ("metadata", "simple"):
        _DEFAULT_FILENAME_FORMAT = filename_format


# Module-level toggle for hiding untouched originals of edited photos via
# the ``.original.bak`` suffix convention. ``sync_photos`` sets this once
# per sync run from ``photos.preserve_originals_as_bak``.
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
    photo,
    file_size: str,
    filename_format: str | None = None,
) -> str:
    """Generate filename for a photo asset.

    Two conventions (controlled by ``filename_format`` or module default):
    - ``"metadata"`` (default): ``name__filesize__base64id.extension``
    - ``"simple"``: ``name.extension``

    When ``_PRESERVE_ORIGINALS_AS_BAK`` is on AND this is the ``original``
    size AND the asset has an ``original_alt`` version on iCloud (edited),
    the filename ends with ``.original.bak`` so photo browsers skip it but
    the file remains filesystem-recoverable.

    Works uniformly across both ``filename_format`` modes — the
    ``.original.bak`` qualifier is appended to whatever the base filename
    would have been (``name__filesize__base64id.ext`` in metadata mode or
    ``name.ext`` in simple mode).

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)
        filename_format: ``"metadata"`` or ``"simple"``, or ``None`` to
            use the module-level default.

    Returns:
        Filename string in the chosen format, plus ``.original.bak`` suffix
        when the bak-preservation toggle applies to this file. The bak suffix
        is appended AFTER the base filename is composed, so it works the same
        whether the base came from ``simple`` (``IMG_1234.HEIC``) or
        ``metadata`` (``IMG_1234__original__<id>.HEIC``) mode.
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
            f"photos.file_format rendered an empty name for {file_size}; falling back to {filename_format} naming.",
        )

    if filename_format == "simple":
        result = name if extension == "" else f"{name}.{extension}"
    else:
        photo_id_encoded = base64.urlsafe_b64encode(photo.id.encode()).decode()
        if extension == "":
            result = f"{'__'.join([name, file_size, photo_id_encoded])}"
        else:
            result = f"{'__'.join([name, file_size, photo_id_encoded])}.{extension}"

    # Apply .original.bak hide-suffix when applicable. Uniformly handled for
    # both filename_format modes — simple+bak yields IMG_1234.HEIC.original.bak,
    # metadata+bak yields IMG_1234__original__<id>.HEIC.original.bak.
    if _PRESERVE_ORIGINALS_AS_BAK and file_size == "original" and _photo_has_alt_version(photo):
        result = f"{result}.original.bak"

    return result


def resolve_folder_path(destination_path: str, folder_format: str | None, photo) -> str:
    """Compute the folder path for a photo WITHOUT touching the filesystem.

    Same result as ``create_folder_path_if_needed`` but never creates the
    directory. Read-only callers (e.g. the ``--dry-run`` migration checker)
    use this so a preview never writes to disk.

    Args:
        destination_path: Base destination path
        folder_format: strftime format string for folder creation (e.g., "%Y/%m")
        photo: Photo object with created date

    Returns:
        Full destination path including the created-date folder if folder_format is set
    """
    if folder_format is None:
        return destination_path
    folder = photo.created.strftime(folder_format)
    return os.path.join(destination_path, folder)


def create_folder_path_if_needed(
    destination_path: str, folder_format: str | None, photo,
) -> str:
    """Resolve the folder path and create it on disk if folder_format is set.

    Args:
        destination_path: Base destination path
        folder_format: strftime format string for folder creation (e.g., "%Y/%m")
        photo: Photo object with created date

    Returns:
        Full destination path including created folder if folder_format is specified
    """
    full_destination = resolve_folder_path(destination_path, folder_format, photo)
    if folder_format is not None:
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

    if not os.path.isfile(old_path):
        return
    if os.path.isfile(new_path):
        LOGGER.warning(f"Renaming {old_path} over existing {new_path}")
    else:
        LOGGER.info(f"Renaming {old_path} -> {new_path}")
    os.rename(old_path, new_path)


def _get_video_filetype_mapping() -> dict:
    """Get mapping of Live Photo paired-video Apple UTI types to extensions.

    Live Photo videos are QuickTime movies; iCloud reports the UTI in the
    version's ``type`` field. Anything not listed falls back to ``MOV`` (the
    only container Apple has ever used for the Live Photo motion component).

    Returns:
        Dictionary mapping Apple UTI type strings to file extensions
    """
    return {
        "com.apple.quicktime-movie": "MOV",
        "public.mpeg-4": "MP4",
    }


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
