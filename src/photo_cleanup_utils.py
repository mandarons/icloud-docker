"""Photo file cleanup utilities module.

This module contains utilities for cleaning up obsolete photo files
that are no longer on the server.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"

from pathlib import Path

from src import get_logger

LOGGER = get_logger()


def remove_obsolete_files(destination_path: str | None, tracked_files: set[str] | None) -> set[str]:
    """Remove local obsolete files that are no longer on server.

    Args:
        destination_path: Path to search for obsolete files
        tracked_files: Set of files that should be kept (files on server)

    Returns:
        Set of paths that were removed
    """
    removed_paths = set()

    if not (destination_path and tracked_files is not None):
        return removed_paths

    for path in Path(destination_path).rglob("*"):
        local_file = str(path.absolute())
        if local_file not in tracked_files:
            if path.is_file():
                LOGGER.info(f"Removing {local_file} ...")
                path.unlink(missing_ok=True)
                removed_paths.add(local_file)

    return removed_paths
