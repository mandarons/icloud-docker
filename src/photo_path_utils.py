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


def generate_photo_filename_with_metadata(photo, file_size: str) -> str:
    """Generate filename with file size and photo ID metadata.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)

    Returns:
        Filename string with format: name__filesize__base64id.extension
    """
    name, extension = get_photo_name_and_extension(photo, file_size)
    photo_id_encoded = base64.urlsafe_b64encode(photo.id.encode()).decode()

    if extension == "":
        return f"{'__'.join([name, file_size, photo_id_encoded])}"
    else:
        return f"{'__'.join([name, file_size, photo_id_encoded])}.{extension}"


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

    if os.path.isfile(old_path):
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
