"""File download utilities.

This module provides file downloading functionality for iCloud Drive sync,
separating download logic from sync operations per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import time
from typing import Any

from icloudpy import exceptions

from src import configure_icloudpy_logging, get_logger
from src.drive_package_processing import process_package

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def download_file(item: Any, local_file: str) -> str | None:
    """Download a file from iCloud to local filesystem.

    This function handles the actual download of files from iCloud, including
    package detection and processing, and sets the correct modification time.

    Args:
        item: iCloud file item to download
        local_file: Local path to save the file

    Returns:
        Path to the downloaded/processed file, or None if download failed
    """
    if not (item and local_file):
        return None

    LOGGER.info(f"Downloading {local_file} ...")
    try:
        with item.open(stream=True) as response:
            with open(local_file, "wb") as file_out:
                for chunk in response.iter_content(4 * 1024 * 1024):
                    file_out.write(chunk)

            # Check if this is a package that needs processing
            if response.url and "/packageDownload?" in response.url:
                processed_file = process_package(local_file=local_file)
                if processed_file:
                    local_file = processed_file
                else:
                    return None

        # Set the file modification time to match the remote file
        item_modified_time = time.mktime(item.date_modified.timetuple())
        os.utime(local_file, (item_modified_time, item_modified_time))

    except (exceptions.ICloudPyAPIResponseException, FileNotFoundError, Exception) as e:
        LOGGER.error(f"Failed to download {local_file}: {e!s}")
        return None

    return local_file
