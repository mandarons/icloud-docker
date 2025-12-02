"""Photo file operations module.

This module contains utilities for photo file operations including
downloading, hardlink creation, and file existence checking.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"

import os
import shutil
import time

from src import get_logger

LOGGER = get_logger()


def check_photo_exists(photo, file_size: str, local_path: str) -> bool:
    """Check if photo exists locally with correct size.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)
        local_path: Local file path to check

    Returns:
        True if photo exists locally with correct size, False otherwise
    """
    if not (photo and local_path and os.path.isfile(local_path)):
        return False

    local_size = os.path.getsize(local_path)
    remote_size = int(photo.versions[file_size]["size"])

    if local_size == remote_size:
        LOGGER.debug(f"No changes detected. Skipping the file {local_path} ...")
        return True
    else:
        LOGGER.debug(f"Change detected: local_file_size is {local_size} and remote_file_size is {remote_size}.")
        return False


def create_hardlink(source_path: str, destination_path: str) -> bool:
    """Create a hard link from source to destination.

    Args:
        source_path: Path to existing file to link from
        destination_path: Path where hardlink should be created

    Returns:
        True if hardlink was created successfully, False otherwise
    """
    try:
        # Ensure destination directory exists
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        # Create hard link
        os.link(source_path, destination_path)
        LOGGER.info(f"Created hard link: {destination_path} (linked to existing file: {source_path})")
        return True
    except (OSError, FileNotFoundError) as e:
        LOGGER.warning(f"Failed to create hard link {destination_path}: {e!s}")
        return False


def download_photo_from_server(photo, file_size: str, destination_path: str, max_retries: int = 1) -> bool:
    """Download photo from iCloud server to local path.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)
        destination_path: Local path where photo should be saved
        max_retries: Maximum number of retries on 410 errors (default: 1)

    Returns:
        True if download was successful, False otherwise
    """
    if not (photo and file_size and destination_path):
        return False

    LOGGER.info(f"Downloading {destination_path} ...")

    retries = 0
    while retries <= max_retries:  # noqa: PERF203
        try:
            download = photo.download(file_size)
            with open(destination_path, "wb") as file_out:
                shutil.copyfileobj(download.raw, file_out)

            # Set file modification time to photo's added date
            local_modified_time = time.mktime(photo.added_date.timetuple())
            os.utime(destination_path, (local_modified_time, local_modified_time))

            return True

        except Exception as e:  # noqa: PERF203
            # Enhanced error logging with file path context
            # This catches all exceptions including iCloudPy errors like ObjectNotFoundException
            error_msg = str(e)

            # Check for HTTP 410 Gone error - download URL has expired
            if "Gone (410)" in error_msg or "410" in error_msg:
                if retries < max_retries:
                    retries += 1
                    LOGGER.warning(
                        f"Download URL expired (410) for {destination_path}. "
                        f"Refreshing URL and retrying (attempt {retries}/{max_retries})...",
                    )
                    # Clear cached versions to force URL refresh on next download attempt
                    if hasattr(photo, "_versions"):
                        photo._versions = None  # noqa: SLF001
                    continue
                else:
                    LOGGER.error(
                        f"Failed to download {destination_path} after {max_retries} retries: {error_msg}",
                    )
                    return False

            # Handle other errors
            if "ObjectNotFoundException" in error_msg or "NOT_FOUND" in error_msg:
                LOGGER.error(f"Photo not found in iCloud Photos - {destination_path}: {error_msg}")
            else:
                LOGGER.error(f"Failed to download {destination_path}: {error_msg}")
            return False

    return False


def rename_legacy_file_if_exists(old_path: str, new_path: str) -> None:
    """Rename legacy file format to new format if it exists.

    Args:
        old_path: Path to legacy file format
        new_path: Path to new file format
    """
    if os.path.isfile(old_path):
        os.rename(old_path, new_path)
