"""Drive filtering utilities.

This module provides filtering functionality for iCloud Drive sync operations,
separating file and folder filtering logic from the main sync logic per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import re
from pathlib import Path, PurePath

from src import configure_icloudpy_logging, get_logger

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def wanted_file(filters: list[str] | None, ignore: list[str] | None, file_path: str) -> bool:
    """Check if a file should be synced based on filters and ignore patterns.

    Args:
        filters: List of file extension patterns to include (None means include all)
        ignore: List of ignore patterns to exclude
        file_path: Path to the file to check

    Returns:
        True if file should be synced, False otherwise
    """
    if not file_path:
        return False

    if ignore and _is_ignored_path(ignore, file_path):
        LOGGER.debug(f"Skipping the unwanted file {file_path}")
        return False

    if not filters or len(filters) == 0:
        return True

    for file_extension in filters:
        if re.search(f"{file_extension}$", file_path, re.IGNORECASE):
            return True

    LOGGER.debug(f"Skipping the unwanted file {file_path}")
    return False


def wanted_folder(
    filters: list[str] | None,
    ignore: list[str] | None,
    root: str,
    folder_path: str,
) -> bool:
    """Check if a folder should be synced based on filters and ignore patterns.

    Args:
        filters: List of folder paths to include (None means include all)
        ignore: List of ignore patterns to exclude
        root: Root directory path for relative path calculations
        folder_path: Path to the folder to check

    Returns:
        True if folder should be synced, False otherwise
    """
    if ignore and _is_ignored_path(ignore, folder_path):
        return False

    if not filters or not folder_path or not root or len(filters) == 0:
        # Nothing to filter, return True
        return True

    # Something to filter
    folder_path = Path(folder_path)
    for folder in filters:
        child_path = Path(os.path.join(os.path.abspath(root), str(folder).removeprefix("/").removesuffix("/")))
        if folder_path in child_path.parents or child_path in folder_path.parents or folder_path == child_path:
            return True
    return False


def wanted_parent_folder(
    filters: list[str] | None,
    ignore: list[str] | None,
    root: str,
    folder_path: str,
) -> bool:
    """Check if a parent folder should be processed based on filters.

    Args:
        filters: List of folder paths to include (None means include all)
        ignore: List of ignore patterns to exclude
        root: Root directory path for relative path calculations
        folder_path: Path to the parent folder to check

    Returns:
        True if parent folder should be processed, False otherwise
    """
    if not filters or not folder_path or not root or len(filters) == 0:
        return True

    folder_path = Path(folder_path)
    for folder in filters:
        child_path = Path(os.path.join(os.path.abspath(root), folder.removeprefix("/").removesuffix("/")))
        if child_path in folder_path.parents or folder_path == child_path:
            return True
    return False


def _is_ignored_path(ignore_list: list[str], path: str) -> bool:
    """Check if a path matches any ignore pattern.

    Args:
        ignore_list: List of ignore patterns
        path: Path to check against patterns

    Returns:
        True if path should be ignored, False otherwise
    """
    for ignore in ignore_list:
        if PurePath(path).match(ignore + "*" if ignore.endswith("/") else ignore):
            return True
    return False


# Legacy alias for backward compatibility
ignored_path = _is_ignored_path
