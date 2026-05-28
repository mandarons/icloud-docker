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
import unicodedata
from urllib.parse import unquote

from src import get_logger

LOGGER = get_logger()


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
            LOGGER.warning(f"Unknown filetype {filetype} for original_alt version of {filename}")

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


def generate_photo_filename_with_metadata(photo, file_size: str) -> str:
    """Generate filename with file size and photo ID metadata.

    When the ``_PRESERVE_ORIGINALS_AS_BAK`` toggle is on AND this file is the
    ``original`` size AND the asset has an ``original_alt`` version on iCloud
    (i.e. the user has edited it in Photos.app), the filename ends with
    ``.original.bak`` so photo browsers skip it but the file remains
    filesystem-recoverable. This pairs with downloading ``original_alt``
    separately to give the user a visible "current view" file plus a hidden
    "untouched original" sidecar.

    Works uniformly across both ``filename_format`` modes — the
    ``.original.bak`` qualifier is appended to whatever the base filename
    would have been (``name__filesize__base64id.ext`` in metadata mode or
    ``name.ext`` in simple mode).

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)

    Returns:
        Filename string in the chosen format, plus ``.original.bak`` suffix
        when the bak-preservation toggle applies to this file.
    """
    name, extension = get_photo_name_and_extension(photo, file_size)
    photo_id_encoded = base64.urlsafe_b64encode(photo.id.encode()).decode()

    if extension == "":
        result = f"{'__'.join([name, file_size, photo_id_encoded])}"
    else:
        result = f"{'__'.join([name, file_size, photo_id_encoded])}.{extension}"

    # Apply .original.bak hide-suffix when applicable. Runs after the base
    # filename is composed, so it works the same regardless of which naming
    # convention generated the base.
    if (
        _PRESERVE_ORIGINALS_AS_BAK
        and file_size == "original"
        and _photo_has_alt_version(photo)
    ):
        result = f"{result}.original.bak"

    return result


def create_folder_path_if_needed(destination_path: str, folder_format: str | None, photo) -> str:
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
