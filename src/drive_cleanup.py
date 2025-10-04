"""Drive cleanup utilities.

This module provides cleanup functionality for removing obsolete files
and directories during iCloud Drive sync operations per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

from pathlib import Path
from shutil import rmtree

from src import configure_icloudpy_logging, get_logger

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def remove_obsolete(destination_path: str, files: set[str]) -> set[str]:
    """Remove local files and directories that no longer exist remotely.

    Args:
        destination_path: Root directory to clean up
        files: Set of file paths that should be kept (exist remotely)

    Returns:
        Set of paths that were removed
    """
    removed_paths = set()
    if not (destination_path and files is not None):
        return removed_paths

    for path in Path(destination_path).rglob("*"):
        local_file = str(path.absolute())
        if local_file not in files:
            LOGGER.info(f"Removing {local_file} ...")
            if path.is_file():
                path.unlink(missing_ok=True)
                removed_paths.add(local_file)
            elif path.is_dir():
                rmtree(local_file)
                removed_paths.add(local_file)
    return removed_paths
