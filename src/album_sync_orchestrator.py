"""Album synchronization orchestration module.

This module contains the main album sync orchestration logic
that coordinates photo filtering, download collection, and parallel execution.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"

import os
from typing import Optional

from src import get_logger
from src.hardlink_registry import HardlinkRegistry
from src.photo_download_manager import (
    collect_download_task,
    execute_parallel_downloads,
)
from src.photo_filter_utils import is_photo_wanted
from src.photo_path_utils import normalize_file_path

LOGGER = get_logger()


def sync_album_photos(
    album,
    destination_path: str,
    file_sizes: list[str],
    extensions: Optional[list[str]] = None,
    files: Optional[set[str]] = None,
    folder_format: Optional[str] = None,
    hardlink_registry: Optional[HardlinkRegistry] = None,
    config=None,
) -> Optional[bool]:
    """Sync photos from given album.

    This function orchestrates the synchronization of a single album by:
    1. Creating the destination directory
    2. Collecting download tasks for wanted photos
    3. Executing downloads in parallel
    4. Recursively syncing subalbums

    Args:
        album: Album object from iCloudPy
        destination_path: Path where photos should be saved
        file_sizes: List of file size variants to download
        extensions: List of allowed file extensions (None = all allowed)
        files: Set to track downloaded files
        folder_format: strftime format string for folder organization
        hardlink_registry: Registry for tracking downloaded files for hardlinks
        config: Configuration dictionary

    Returns:
        True on success, None on invalid input
    """
    if album is None or destination_path is None or file_sizes is None:
        return None

    # Create destination directory with normalized path
    normalized_destination = normalize_file_path(destination_path)
    os.makedirs(normalized_destination, exist_ok=True)
    LOGGER.info(f"Syncing {album.title}")

    # Collect download tasks for photos
    download_tasks = _collect_album_download_tasks(
        album,
        normalized_destination,
        file_sizes,
        extensions,
        files,
        folder_format,
        hardlink_registry,
    )

    # Execute downloads in parallel if there are tasks
    if download_tasks:
        execute_parallel_downloads(download_tasks, config)

    # Recursively sync subalbums
    _sync_subalbums(
        album,
        normalized_destination,
        file_sizes,
        extensions,
        files,
        folder_format,
        hardlink_registry,
        config,
    )

    return True


def _collect_album_download_tasks(
    album,
    destination_path: str,
    file_sizes: list[str],
    extensions: Optional[list[str]],
    files: Optional[set[str]],
    folder_format: Optional[str],
    hardlink_registry: Optional[HardlinkRegistry],
) -> list:
    """Collect download tasks for all photos in an album.

    Args:
        album: Album object from iCloudPy
        destination_path: Path where photos should be saved
        file_sizes: List of file size variants to download
        extensions: List of allowed file extensions
        files: Set to track downloaded files
        folder_format: strftime format string for folder organization
        hardlink_registry: Registry for tracking downloaded files

    Returns:
        List of download tasks to execute
    """
    download_tasks = []

    for photo in album:
        if is_photo_wanted(photo, extensions):
            for file_size in file_sizes:
                download_info = collect_download_task(
                    photo,
                    file_size,
                    destination_path,
                    files,
                    folder_format,
                    hardlink_registry,
                )
                if download_info:
                    download_tasks.append(download_info)
        else:
            LOGGER.debug(f"Skipping the unwanted photo {photo.filename}.")

    return download_tasks


def _sync_subalbums(
    album,
    destination_path: str,
    file_sizes: list[str],
    extensions: Optional[list[str]],
    files: Optional[set[str]],
    folder_format: Optional[str],
    hardlink_registry: Optional[HardlinkRegistry],
    config,
) -> None:
    """Recursively sync all subalbums.

    Args:
        album: Album object from iCloudPy
        destination_path: Base path where subalbums should be created
        file_sizes: List of file size variants to download
        extensions: List of allowed file extensions
        files: Set to track downloaded files
        folder_format: strftime format string for folder organization
        hardlink_registry: Registry for tracking downloaded files
        config: Configuration dictionary
    """
    for subalbum in album.subalbums:
        sync_album_photos(
            album.subalbums[subalbum],
            os.path.join(destination_path, subalbum),
            file_sizes,
            extensions,
            files,
            folder_format,
            hardlink_registry,
            config,
        )
