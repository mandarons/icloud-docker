"""File existence checking utilities.

This module provides file and package existence checking functionality,
separating existence validation logic from sync operations per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
from datetime import timezone
from pathlib import Path
from shutil import rmtree
from typing import Any

from src import DEFAULT_REQUEST_TIMEOUT_SEC, configure_icloudpy_logging, get_logger

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
    # iCloudPy produces date_modified via strptime(..., "%Y-%m-%dT%H:%M:%SZ") — always
    # naive UTC with no tzinfo. replace(tzinfo=UTC) is the correct conversion.
    remote_file_modified_time = int(item.date_modified.replace(tzinfo=timezone.utc).timestamp())
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
    # iCloudPy produces date_modified via strptime(..., "%Y-%m-%dT%H:%M:%SZ") — always
    # naive UTC with no tzinfo. replace(tzinfo=UTC) is the correct conversion.
    remote_package_modified_time = int(item.date_modified.replace(tzinfo=timezone.utc).timestamp())
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


def package_bundle_unchanged(item: Any, local_file: str) -> bool:
    """Freshness check for a package stored as a flat single-file bundle.

    A flattened package -- an unrecognised-mime package kept as-is, or any
    package downloaded with ``flatten_packages: true`` -- lands on disk as a
    single file whose byte count is the size of the package-download archive,
    NOT ``item.size`` (the package's *logical* size that iCloud reports). So
    ``file_exists`` always sees a spurious size mismatch for these and
    re-downloads the bundle on every sync.

    ``download_file`` stamps the bundle's mtime to ``item.date_modified`` via
    ``os.utime``, and iCloud bumps ``date_modified`` whenever a package's
    contents change, so the mtime is the reliable change signal. Match on mtime
    alone (the same mtime comparison ``file_exists`` uses), skipping the
    unusable size check.

    Args:
        item: iCloud package item with a ``date_modified`` attribute
        local_file: Path to the local single-file bundle

    Returns:
        True if the bundle is present and its mtime matches the remote
        (unchanged -- skip the re-download), False otherwise.
    """
    if not (item and local_file and os.path.isfile(local_file)):
        return False
    # iCloudPy produces date_modified as naive UTC (strptime ...Z); replace(tzinfo=UTC)
    # matches the convention file_exists/package_exists use so mtimes are TZ-invariant.
    return int(os.path.getmtime(local_file)) == int(item.date_modified.replace(tzinfo=timezone.utc).timestamp())


def is_package(item: Any, timeout: int = DEFAULT_REQUEST_TIMEOUT_SEC) -> bool:
    """Determine if an iCloud item is a package that needs special handling.

    Args:
        item: iCloud item to check
        timeout: HTTP read timeout in seconds (default: DEFAULT_REQUEST_TIMEOUT_SEC)

    Returns:
        True if item is a package, False otherwise
    """
    file_is_a_package = False
    try:
        with item.open(stream=True, timeout=timeout) as response:
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
