"""Drive sync directory orchestration.

This module provides the main sync directory coordination functionality,
orchestrating folder processing, file collection, and parallel downloads per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import unicodedata
from typing import Any

from src import configure_icloudpy_logging, get_logger, sync_drive
from src.drive_cleanup import remove_obsolete
from src.drive_filtering import wanted_parent_folder
from src.drive_folder_processing import process_folder
from src.drive_parallel_download import collect_file_for_download, execute_parallel_downloads

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def sync_directory(
    drive: Any,
    destination_path: str,
    items: Any,
    root: str,
    top: bool = True,
    filters: dict[str, list[str]] | None = None,
    ignore: list[str] | None = None,
    remove: bool = False,
    config: Any | None = None,
) -> set[str]:
    """Synchronize a directory from iCloud Drive to local filesystem.

    This function orchestrates the entire sync process by:
    1. Processing folders and recursively syncing subdirectories
    2. Collecting files for parallel download
    3. Executing parallel downloads
    4. Cleaning up obsolete files if requested

    Args:
        drive: iCloud drive service instance
        destination_path: Local destination directory
        items: iCloud items to process
        root: Root directory for relative path calculations
        top: Whether this is the top-level sync call
        filters: Dictionary of filters (folders, file_extensions)
        ignore: List of ignore patterns
        remove: Whether to remove obsolete local files
        config: Configuration object

    Returns:
        Set of all processed file paths
    """
    files = set()
    download_tasks = []

    if not (drive and destination_path and items and root):
        return files

    # First pass: process folders and collect download tasks
    for i in items:
        item = drive[i]

        if item.type in ("folder", "app_library"):
            _process_folder_item(
                item,
                destination_path,
                filters,
                ignore,
                root,
                files,
                config,
            )
        elif item.type == "file":
            _process_file_item(
                item,
                destination_path,
                filters,
                ignore,
                root,
                files,
                download_tasks,
            )

    # Second pass: execute downloads in parallel
    if download_tasks:
        _execute_downloads(download_tasks, config)

    # Final cleanup if this is the top-level call
    if top and remove:
        remove_obsolete(destination_path=destination_path, files=files)

    return files


def _process_folder_item(
    item: Any,
    destination_path: str,
    filters: dict[str, list[str]] | None,
    ignore: list[str] | None,
    root: str,
    files: set[str],
    config: Any | None,
) -> None:
    """Process a single folder item.

    Args:
        item: iCloud folder item
        destination_path: Local destination directory
        filters: Dictionary of filters
        ignore: List of ignore patterns
        root: Root directory
        files: Set to update with processed files
        config: Configuration object
    """
    new_folder = process_folder(
        item=item,
        destination_path=destination_path,
        filters=filters["folders"] if filters and "folders" in filters else None,
        ignore=ignore,
        root=root,
    )
    if not new_folder:
        return

    try:
        files.add(unicodedata.normalize("NFC", new_folder))
        # Recursively sync subdirectory
        subdirectory_files = sync_directory(
            drive=item,
            destination_path=new_folder,
            items=item.dir(),
            root=root,
            top=False,
            filters=filters,
            ignore=ignore,
            config=config,
        )
        files.update(subdirectory_files)
    except Exception:
        # Continue execution to next item, without crashing the app
        pass


def _process_file_item(
    item: Any,
    destination_path: str,
    filters: dict[str, list[str]] | None,
    ignore: list[str] | None,
    root: str,
    files: set[str],
    download_tasks: list[dict[str, Any]],
) -> None:
    """Process a single file item.

    Args:
        item: iCloud file item
        destination_path: Local destination directory
        filters: Dictionary of filters
        ignore: List of ignore patterns
        root: Root directory
        files: Set to update with processed files
        download_tasks: List to append download tasks to
    """
    if not wanted_parent_folder(
        filters=filters["folders"] if filters and "folders" in filters else None,
        ignore=ignore,
        root=root,
        folder_path=destination_path,
    ):
        return

    try:
        download_info = collect_file_for_download(
            item=item,
            destination_path=destination_path,
            filters=filters["file_extensions"] if filters and "file_extensions" in filters else None,
            ignore=ignore,
            files=files,
        )
        if download_info:
            download_tasks.append(download_info)
    except Exception:
        # Continue execution to next item, without crashing the app
        pass


def _execute_downloads(download_tasks: list[dict[str, Any]], config: Any) -> None:
    """Execute parallel downloads.

    Args:
        download_tasks: List of download task dictionaries
        config: Configuration object
    """
    max_threads = sync_drive.get_max_threads(config)
    execute_parallel_downloads(download_tasks, max_threads)
