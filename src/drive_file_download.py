"""File download utilities.

This module provides file downloading functionality for iCloud Drive sync,
separating download logic from sync operations per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import time
from typing import Any

from src import configure_icloudpy_logging, get_logger
from src.drive_package_processing import process_package

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def download_file(
    item: Any, local_file: str, flatten_packages: bool = False,
) -> str | None:
    """Download a file from iCloud to local filesystem.

    This function handles the actual download of files from iCloud, including
    package detection and processing, and sets the correct modification time.

    Args:
        item: iCloud file item to download
        local_file: Local path to save the file
        flatten_packages: When True, package downloads (``/packageDownload?``
            URLs) skip the unpack step entirely and stay on disk as a
            single binary file. Useful for backup-style deployments where
            bundle-directory semantics aren't needed and single-file
            storage simplifies dedup / restoration. Opt-in via
            ``drive.flatten_packages: true`` in config.yaml.

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

            # Check if this is a package that needs processing.
            #
            # ``process_package`` now returns the local_file path for both
            # successful unpacks AND unrecognised mime types (the bytes
            # are still on disk as a flat bundle — see the docstring on
            # ``process_package`` for the rationale). It only returns
            # ``None`` on hard processing failure that leaves the file in
            # an unusable state. So we surface that as a download failure
            # but no longer treat "couldn't unpack" as failure when the
            # downloaded bytes are intact.
            if response.url and "/packageDownload?" in response.url:
                processed_file = process_package(
                    local_file=local_file, flatten=flatten_packages,
                )
                if processed_file is None:
                    return None
                local_file = processed_file

        # Set the file modification time to match the remote file
        item_modified_time = time.mktime(item.date_modified.timetuple())
        os.utime(local_file, (item_modified_time, item_modified_time))

    except Exception as e:
        # Enhanced error logging with file path context
        # This catches all exceptions including iCloudPy errors like ObjectNotFoundException
        error_msg = str(e)
        if "ObjectNotFoundException" in error_msg or "NOT_FOUND" in error_msg:
            LOGGER.error(f"File not found in iCloud Drive - {local_file}: {error_msg}")
        else:
            LOGGER.error(f"Failed to download {local_file}: {error_msg}")
        return None

    return local_file
