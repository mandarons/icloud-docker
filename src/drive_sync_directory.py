"""Drive sync directory orchestration.

This module provides the main sync directory coordination functionality,
orchestrating folder processing, file collection, and parallel downloads per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import unicodedata
from typing import Any
from urllib.parse import unquote

from src import config_parser, configure_icloudpy_logging, get_logger, recycle_bin, sync_drive
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

        if _shared_with_me(item):
            _keep_what_is_here(item, destination_path, files)
            continue
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
                config,
            )

    # Second pass: execute downloads in parallel
    if download_tasks:
        _execute_downloads(download_tasks, config)

    # Final cleanup if this is the top-level call
    if top and remove:
        remove_obsolete(
            destination_path=destination_path,
            files=files,
            recycle_bin=recycle_bin.from_config(config, "drive"),
            exclude_filenames={config_parser.get_mount_marker_filename(config or {})},
        )

    return files


def _shared_with_me(item: Any) -> bool:
    """Whether someone else owns this item and shared it with this account.

    iCloud lists such a folder in the recipient's Drive (``share: TO_ME``,
    with the owner named), but downloading it through the recipient fails
    with NOT_FOUND, and its owner's own backup is where it belongs. So it is
    skipped. What an earlier sync already copied is kept, not cleaned up.
    """
    data = getattr(item, "data", None)
    return isinstance(data, dict) and data.get("share") == "TO_ME"


def _keep_what_is_here(item: Any, destination_path: str, files: set[str]) -> None:
    """Skip a shared-with-me item, keeping any local copy out of cleanup."""
    local = os.path.join(destination_path, unquote(item.name))
    LOGGER.info(f"Skipping {local}: shared with this account by its owner, whose backup has it")
    files.add(unicodedata.normalize("NFC", local))
    for folder, dirs, names in os.walk(local):
        for name in dirs + names:
            files.add(unicodedata.normalize("NFC", os.path.join(folder, name)))


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
    config: Any | None = None,
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
        config: Configuration object
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
            config=config,
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
