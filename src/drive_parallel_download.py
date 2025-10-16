"""Parallel download utilities.

This module provides parallel download coordination for iCloud Drive sync,
separating parallel execution logic from sync operations per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import unquote

from src import configure_icloudpy_logging, get_logger
from src.drive_file_download import download_file
from src.drive_file_existence import file_exists, is_package, package_exists
from src.drive_filtering import wanted_file

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()

# Thread-safe lock for file set operations
files_lock = Lock()


def collect_file_for_download(
    item: Any,
    destination_path: str,
    filters: list[str] | None,
    ignore: list[str] | None,
    files: set[str],
) -> dict[str, Any] | None:
    """Collect file information for parallel download without immediately downloading.

    Args:
        item: iCloud file item
        destination_path: Local destination directory
        filters: File extension filters
        ignore: Ignore patterns
        files: Set to track processed files (thread-safe updates)

    Returns:
        Download task info dict, or None if file should be skipped
    """
    if not (item and destination_path and files is not None):
        return None

    # Decode URL-encoded filename from iCloud API
    # This handles special characters like %CC%88 (combining diacritical marks)
    decoded_name = unquote(item.name)
    local_file = os.path.join(destination_path, decoded_name)
    local_file = unicodedata.normalize("NFC", local_file)

    if not wanted_file(filters=filters, ignore=ignore, file_path=local_file):
        return None

    # Thread-safe file set update
    with files_lock:
        files.add(local_file)

    item_is_package = is_package(item=item)
    if item_is_package:
        if package_exists(item=item, local_package_path=local_file):
            with files_lock:
                for f in Path(local_file).glob("**/*"):
                    files.add(str(f))
            return None
    elif file_exists(item=item, local_file=local_file):
        return None

    # Return download task info
    return {
        "item": item,
        "local_file": local_file,
        "is_package": item_is_package,
        "files": files,
    }


def download_file_task(download_info: dict[str, Any]) -> bool:
    """Download a single file as part of parallel execution.

    Args:
        download_info: Dictionary containing download task information

    Returns:
        True if download succeeded, False otherwise
    """
    item = download_info["item"]
    local_file = download_info["local_file"]
    is_package = download_info["is_package"]
    files = download_info["files"]

    LOGGER.debug(f"[Thread] Starting download of {local_file}")

    try:
        downloaded_file = download_file(item=item, local_file=local_file)
        if not downloaded_file:
            return False

        if is_package:
            with files_lock:
                for f in Path(downloaded_file).glob("**/*"):
                    f = str(f)
                    f_normalized = unicodedata.normalize("NFD", f)
                    if os.path.exists(f):
                        os.rename(f, f_normalized)
                        files.add(f_normalized)

        LOGGER.debug(f"[Thread] Completed download of {local_file}")
        return True
    except Exception as e:
        LOGGER.error(f"[Thread] Failed to download {local_file}: {e!s}")
        return False


def execute_parallel_downloads(download_tasks: list[dict[str, Any]], max_threads: int) -> tuple[int, int]:
    """Execute multiple file downloads in parallel.

    Args:
        download_tasks: List of download task dictionaries
        max_threads: Maximum number of concurrent threads

    Returns:
        Tuple of (successful_downloads, failed_downloads) counts
    """
    if not download_tasks:
        return 0, 0

    LOGGER.info(f"Starting parallel downloads with {max_threads} threads for {len(download_tasks)} files...")

    successful_downloads = 0
    failed_downloads = 0

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        # Submit all download tasks
        future_to_task = {executor.submit(download_file_task, task): task for task in download_tasks}

        # Process completed downloads
        for future in as_completed(future_to_task):
            try:
                result = future.result()
                if result:
                    successful_downloads += 1
                else:
                    failed_downloads += 1
            except Exception as e:  # noqa: PERF203
                LOGGER.error(f"Download task failed with exception: {e!s}")
                failed_downloads += 1

    LOGGER.info(f"Parallel downloads completed: {successful_downloads} successful, {failed_downloads} failed")
    return successful_downloads, failed_downloads
