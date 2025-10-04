"""Folder processing utilities.

This module provides folder creation and processing functionality for
iCloud Drive sync operations, separating folder logic from sync operations per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import unicodedata
from typing import Any, Optional

from src import configure_icloudpy_logging, get_logger
from src.drive_filtering import wanted_folder

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def process_folder(
    item: Any,
    destination_path: str,
    filters: Optional[list[str]],
    ignore: Optional[list[str]],
    root: str,
) -> Optional[str]:
    """Process a folder item by creating the local directory if wanted.

    Args:
        item: iCloud folder item
        destination_path: Local destination directory
        filters: Folder filters to apply
        ignore: Ignore patterns
        root: Root directory for relative path calculations

    Returns:
        Path to the created directory, or None if folder should be skipped
    """
    if not (item and destination_path and root):
        return None

    new_directory = os.path.join(destination_path, item.name)
    new_directory_norm = unicodedata.normalize("NFC", new_directory)

    if not wanted_folder(filters=filters, ignore=ignore, folder_path=new_directory_norm, root=root):
        LOGGER.debug(f"Skipping the unwanted folder {new_directory} ...")
        return None

    os.makedirs(new_directory_norm, exist_ok=True)
    return new_directory
