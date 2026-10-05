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


def remove_obsolete(destination_path: str, files: set[str], recycle_bin=None) -> set[str]:
    """Remove local files and directories that no longer exist remotely.

    Args:
        destination_path: Root directory to clean up
        files: Set of file paths that should be kept (exist remotely)
        recycle_bin: ``RecycleBin`` to move them to instead of deleting

    Returns:
        Set of paths that were removed
    """
    removed_paths = set()
    if not (destination_path and files is not None):
        return removed_paths
    if recycle_bin:
        recycle_bin.purge()

    for path in Path(destination_path).rglob("*"):
        local_file = str(path.absolute())
        if recycle_bin and recycle_bin.contains(local_file):
            continue
        if local_file not in files:
            if not (path.is_file() or path.is_dir()):
                continue  # already went with a folder removed above
            if recycle_bin:
                LOGGER.info(f"Moving {local_file} to the recycle bin ...")
                recycle_bin.discard(local_file, destination_path)
            else:
                LOGGER.info(f"Removing {local_file} ...")
                if path.is_file():
                    path.unlink(missing_ok=True)
                else:
                    rmtree(local_file)
            removed_paths.add(local_file)
    return removed_paths
