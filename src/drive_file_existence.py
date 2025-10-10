"""File existence checking utilities.

This module provides file and package existence checking functionality,
separating existence validation logic from sync operations per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
from pathlib import Path
from shutil import rmtree
from typing import Any

from src import configure_icloudpy_logging, get_logger

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def file_exists(item: Any, local_file: str) -> bool:
    """Check if a file exists locally and is up-to-date.

    Args:
        item: iCloud file item with date_modified and size attributes
        local_file: Path to the local file

    Returns:
        True if file exists and is up-to-date, False otherwise
    """
    if not (item and local_file and os.path.isfile(local_file)):
        LOGGER.debug(f"File {local_file} does not exist locally.")
        return False

    local_file_modified_time = int(os.path.getmtime(local_file))
    remote_file_modified_time = int(item.date_modified.timestamp())
    local_file_size = os.path.getsize(local_file)
    remote_file_size = item.size

    if local_file_modified_time == remote_file_modified_time and (
        local_file_size == remote_file_size
        or (local_file_size == 0 and remote_file_size is None)
        or (local_file_size is None and remote_file_size == 0)
    ):
        LOGGER.debug(f"No changes detected. Skipping the file {local_file} ...")
        return True

    LOGGER.debug(
        f"Changes detected: local_modified_time is {local_file_modified_time}, "
        + f"remote_modified_time is {remote_file_modified_time}, "
        + f"local_file_size is {local_file_size} and remote_file_size is {remote_file_size}.",
    )
    return False


def package_exists(item: Any, local_package_path: str) -> bool:
    """Check if a package exists locally and is up-to-date.

    Args:
        item: iCloud package item with date_modified and size attributes
        local_package_path: Path to the local package directory

    Returns:
        True if package exists and is up-to-date, False otherwise
    """
    if not (item and local_package_path and os.path.isdir(local_package_path)):
        LOGGER.debug(f"Package {local_package_path} does not exist locally.")
        return False

    local_package_modified_time = int(os.path.getmtime(local_package_path))
    remote_package_modified_time = int(item.date_modified.timestamp())
    local_package_size = sum(f.stat().st_size for f in Path(local_package_path).glob("**/*") if f.is_file())
    remote_package_size = item.size

    if local_package_modified_time == remote_package_modified_time and local_package_size == remote_package_size:
        LOGGER.debug(f"No changes detected. Skipping the package {local_package_path} ...")
        return True

    LOGGER.info(
        f"Changes detected: local_modified_time is {local_package_modified_time}, "
        + f"remote_modified_time is {remote_package_modified_time}, "
        + f"local_package_size is {local_package_size} and remote_package_size is {remote_package_size}.",
    )
    rmtree(local_package_path)
    return False


def is_package(item: Any) -> bool:
    """Determine if an iCloud item is a package that needs special handling.

    Args:
        item: iCloud item to check

    Returns:
        True if item is a package, False otherwise
    """
    file_is_a_package = False
    try:
        with item.open(stream=True) as response:
            file_is_a_package = response.url and "/packageDownload?" in response.url
    except Exception as e:
        # Enhanced error logging with file context
        # This catches all exceptions including iCloudPy errors like ObjectNotFoundException
        error_msg = str(e)
        item_name = getattr(item, "name", "Unknown file")
        if "ObjectNotFoundException" in error_msg or "NOT_FOUND" in error_msg:
            LOGGER.error(f"File not found in iCloud Drive while checking package type - {item_name}: {error_msg}")
        else:
            LOGGER.error(f"Failed to check package type for {item_name}: {error_msg}")
        # Return False if we can't determine package type due to error
        file_is_a_package = False
    return file_is_a_package
