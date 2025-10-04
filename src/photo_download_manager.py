"""Photo download task management module.

This module contains utilities for managing photo download tasks
and parallel execution during photo synchronization.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Optional

from src import config_parser, get_logger
from src.hardlink_registry import HardlinkRegistry
from src.photo_file_utils import create_hardlink, download_photo_from_server
from src.photo_path_utils import (
    create_folder_path_if_needed,
    generate_photo_filename_with_metadata,
    normalize_file_path,
    rename_legacy_file_if_exists,
)

LOGGER = get_logger()

# Thread-safe lock for file set operations
files_lock = Lock()


class DownloadTaskInfo:
    """Information about a photo download task."""

    def __init__(self, photo, file_size: str, photo_path: str,
                 hardlink_source: Optional[str] = None,
                 hardlink_registry: Optional[HardlinkRegistry] = None):
        """Initialize download task info.

        Args:
            photo: Photo object from iCloudPy
            file_size: File size variant (original, medium, thumb, etc.)
            photo_path: Target path for photo download
            hardlink_source: Path to existing file for hardlink creation
            hardlink_registry: Registry for tracking downloaded files
        """
        self.photo = photo
        self.file_size = file_size
        self.photo_path = photo_path
        self.hardlink_source = hardlink_source
        self.hardlink_registry = hardlink_registry


def get_max_threads_for_download(config) -> int:
    """Get maximum number of threads for parallel downloads.

    Args:
        config: Configuration dictionary

    Returns:
        Maximum number of threads to use for downloads
    """
    return config_parser.get_app_max_threads(config)


def generate_photo_path(photo, file_size: str, destination_path: str,
                       folder_format: Optional[str]) -> str:
    """Generate full file path for photo with legacy file renaming.

    This function combines path generation, folder creation, and legacy
    file renaming into a single operation to maintain backward compatibility.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)
        destination_path: Base destination path
        folder_format: strftime format string for folder creation

    Returns:
        Normalized full path where photo should be saved
    """
    # Generate filename with metadata
    filename_with_metadata = generate_photo_filename_with_metadata(photo, file_size)

    # Create folder path if needed
    final_destination = create_folder_path_if_needed(destination_path, folder_format, photo)

    # Generate paths for legacy file format handling
    filename = photo.filename
    name, extension = filename.rsplit(".", 1) if "." in filename else [filename, ""]

    # Legacy file paths that need to be renamed
    file_path = os.path.join(destination_path, filename)
    file_size_path = os.path.join(
        destination_path,
        f"{'__'.join([name, file_size])}" if extension == "" else f"{'__'.join([name, file_size])}.{extension}",
    )

    # Final path with normalization
    final_file_path = os.path.join(final_destination, filename_with_metadata)
    normalized_path = normalize_file_path(final_file_path)

    # Rename legacy files if they exist
    rename_legacy_file_if_exists(file_path, normalized_path)
    rename_legacy_file_if_exists(file_size_path, normalized_path)

    # Handle existing file with different normalization
    if os.path.isfile(final_file_path) and final_file_path != normalized_path:
        rename_legacy_file_if_exists(final_file_path, normalized_path)

    return normalized_path


def collect_download_task(photo, file_size: str, destination_path: str,
                         files: Optional[set[str]], folder_format: Optional[str],
                         hardlink_registry: Optional[HardlinkRegistry]) -> Optional[DownloadTaskInfo]:
    """Collect photo info for parallel download without immediately downloading.

    Args:
        photo: Photo object from iCloudPy
        file_size: File size variant (original, medium, thumb, etc.)
        destination_path: Base destination path
        files: Set to track downloaded files (thread-safe updates)
        folder_format: strftime format string for folder creation
        hardlink_registry: Registry for tracking downloaded files

    Returns:
        DownloadTaskInfo if photo needs to be processed, None if skipped
    """
    # Check if file size exists on server
    if file_size not in photo.versions:
        photo_path = generate_photo_path(photo, file_size, destination_path, folder_format)
        LOGGER.warning(f"File size {file_size} not found on server. Skipping the photo {photo_path} ...")
        return None

    # Generate photo path
    photo_path = generate_photo_path(photo, file_size, destination_path, folder_format)

    # Thread-safe file set update
    if files is not None:
        with files_lock:
            files.add(photo_path)

    # Check if photo already exists with correct size
    from src.photo_file_utils import check_photo_exists
    if check_photo_exists(photo, file_size, photo_path):
        return None

    # Check for existing hardlink source
    hardlink_source = None
    if hardlink_registry is not None:
        hardlink_source = hardlink_registry.get_existing_path(photo.id, file_size)

    return DownloadTaskInfo(
        photo=photo,
        file_size=file_size,
        photo_path=photo_path,
        hardlink_source=hardlink_source,
        hardlink_registry=hardlink_registry,
    )


def execute_download_task(task_info: DownloadTaskInfo) -> bool:
    """Download a single photo or create hardlink as part of parallel execution.

    Args:
        task_info: Download task information

    Returns:
        True if task completed successfully, False otherwise
    """
    LOGGER.debug(f"[Thread] Starting processing of {task_info.photo_path}")

    try:
        # Try hardlink first if source exists
        if task_info.hardlink_source:
            if create_hardlink(task_info.hardlink_source, task_info.photo_path):
                LOGGER.debug(f"[Thread] Created hardlink for {task_info.photo_path}")
                return True
            else:
                # Fallback to download if hard link creation fails
                LOGGER.warning(f"Hard link creation failed, downloading {task_info.photo_path} instead")

        # Download the photo
        result = download_photo_from_server(task_info.photo, task_info.file_size, task_info.photo_path)
        if result and task_info.hardlink_registry is not None:
            # Register for future hard links if enabled
            task_info.hardlink_registry.register_photo_path(
                task_info.photo.id, task_info.file_size, task_info.photo_path,
            )
            LOGGER.debug(f"[Thread] Completed download of {task_info.photo_path}")

        return result

    except Exception as e:
        LOGGER.error(f"[Thread] Failed to process {task_info.photo_path}: {e!s}")
        return False


def execute_parallel_downloads(download_tasks: list[DownloadTaskInfo], config) -> tuple[int, int]:
    """Execute download tasks in parallel using thread pool.

    Args:
        download_tasks: List of download tasks to execute
        config: Configuration dictionary for thread settings

    Returns:
        Tuple of (successful_downloads, failed_downloads)
    """
    if not download_tasks:
        return 0, 0

    max_threads = get_max_threads_for_download(config)

    # Count hardlink tasks vs download tasks for logging
    hardlink_tasks = sum(1 for task in download_tasks if task.hardlink_source)
    download_only_tasks = len(download_tasks) - hardlink_tasks

    if hardlink_tasks > 0:
        LOGGER.info(
            f"Starting parallel processing with {max_threads} threads: "
            f"{hardlink_tasks} hard links, {download_only_tasks} downloads...",
        )
    else:
        LOGGER.info(
            f"Starting parallel photo downloads with {max_threads} threads for {len(download_tasks)} photos...",
        )

    successful_downloads = 0
    failed_downloads = 0

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        # Submit all download tasks
        future_to_task = {executor.submit(execute_download_task, task): task for task in download_tasks}

        # Process completed downloads
        for future in as_completed(future_to_task):
            try:
                result = future.result()
                if result:
                    successful_downloads += 1
                else:
                    failed_downloads += 1
            except Exception as e:  # noqa: PERF203
                LOGGER.error(f"Unexpected error during photo download: {e!s}")
                failed_downloads += 1

    LOGGER.info(f"Photo processing complete: {successful_downloads} successful, {failed_downloads} failed")
    return successful_downloads, failed_downloads
