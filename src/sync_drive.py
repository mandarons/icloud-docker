"""Sync drive module.

This module provides the main entry point for iCloud Drive synchronization,
orchestrating the sync process using specialized utility modules per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import unicodedata
from pathlib import Path
from typing import Any

from src import config_parser, configure_icloudpy_logging, get_logger
from src.drive_cleanup import remove_obsolete  # noqa: F401
from src.drive_file_download import download_file  # noqa: F401
from src.drive_file_existence import file_exists, is_package, package_exists  # noqa: F401
from src.drive_filtering import ignored_path, wanted_file, wanted_folder, wanted_parent_folder  # noqa: F401
from src.drive_folder_processing import process_folder  # noqa: F401
from src.drive_package_processing import process_package  # noqa: F401
from src.drive_parallel_download import collect_file_for_download, download_file_task, files_lock  # noqa: F401
from src.drive_sync_directory import sync_directory
from src.drive_thread_config import get_max_threads  # noqa: F401

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def sync_drive(config: Any, drive: Any) -> set[str]:
    """Synchronize iCloud Drive to local filesystem.

    This function serves as the main entry point for drive synchronization,
    preparing the destination and delegating to the sync_directory orchestrator.

    Args:
        config: Configuration dictionary containing drive settings
        drive: iCloud drive service instance

    Returns:
        Set of all synchronized file paths
    """
    destination_path = config_parser.prepare_drive_destination(config=config)
    return sync_directory(
        drive=drive,
        destination_path=destination_path,
        root=destination_path,
        items=drive.dir(),
        top=True,
        filters=config["drive"]["filters"] if "drive" in config and "filters" in config["drive"] else None,
        ignore=config["drive"]["ignore"] if "drive" in config and "ignore" in config["drive"] else None,
        remove=config_parser.get_drive_remove_obsolete(config=config),
        config=config,
    )


def process_file(item: Any, destination_path: str, filters: list[str], ignore: list[str], files: set[str]) -> bool:
    """Process given item as file (legacy compatibility function).

    This function maintains backward compatibility with existing tests.
    New code should use the specialized modules directly.

    Args:
        item: iCloud file item to process
        destination_path: Local destination directory
        filters: File extension filters
        ignore: Ignore patterns
        files: Set to track processed files

    Returns:
        True if file was processed successfully, False otherwise
    """
    if not (item and destination_path and files is not None):
        return False
    local_file = os.path.join(destination_path, item.name)
    local_file = unicodedata.normalize("NFC", local_file)
    if not wanted_file(filters=filters, ignore=ignore, file_path=local_file):
        return False
    files.add(local_file)
    item_is_package = is_package(item=item)
    if item_is_package:
        if package_exists(item=item, local_package_path=local_file):
            for f in Path(local_file).glob("**/*"):
                files.add(str(f))
            return False
    elif file_exists(item=item, local_file=local_file):
        return False
    local_file = download_file(item=item, local_file=local_file)
    if local_file and item_is_package:
        for f in Path(local_file).glob("**/*"):
            f = str(f)
            f_normalized = unicodedata.normalize("NFD", f)
            if os.path.exists(f):
                os.rename(f, f_normalized)
                files.add(f_normalized)
    return bool(local_file)
