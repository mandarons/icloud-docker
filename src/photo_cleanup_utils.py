"""Photo file cleanup utilities module.

This module contains utilities for cleaning up obsolete photo files
that are no longer on the server.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"

from pathlib import Path

from src import DEFAULT_OBSOLETE_DELETE_LIMIT_PERCENT, get_logger

LOGGER = get_logger()


def remove_obsolete_files(
    destination_path: str | None,
    tracked_files: set[str] | None,
    exclude_filenames: set[str] | None = None,
    limit_percent: int = DEFAULT_OBSOLETE_DELETE_LIMIT_PERCENT,
) -> set[str]:
    """Remove local obsolete files that are no longer on server.

    Args:
        destination_path: Path to search for obsolete files
        tracked_files: Set of files that should be kept (files on server)
        exclude_filenames: Set of filenames (basename only) that must never
            be removed even if they are not in ``tracked_files``.  Used to
            protect the mount-marker sentinel file from cleanup.

    Returns:
        Set of paths that were removed
    """
    removed_paths: set[str] = set()

    if not (destination_path and tracked_files is not None):
        return removed_paths

    # Decide everything before deleting anything. Cleanup is the only
    # destructive step in a sync, and it infers deletions from the absence
    # of a path in ``tracked_files`` -- so any bug that leaves paths
    # untracked reads as "the server no longer has these" and is acted on
    # at full speed. Counting first makes that recoverable.
    candidates = []
    present = 0
    for path in Path(destination_path).rglob("*"):
        if not path.is_file():
            continue
        present += 1
        local_file = str(path.absolute())
        if local_file in tracked_files:
            continue
        if exclude_filenames and path.name in exclude_filenames:
            continue
        candidates.append((path, local_file))

    if not candidates:
        return removed_paths

    if limit_percent > 0 and present:
        share = 100 * len(candidates) / present
        if share > limit_percent:
            LOGGER.error(
                f"Refusing to remove {len(candidates)} of {present} files "
                f"({share:.0f}%) under {destination_path} — over the "
                f"{limit_percent}% obsolete-delete limit. A sync does not "
                f"normally make this share of a library obsolete, so this is "
                f"treated as a fault rather than acted on. Check the library "
                f"is fully enumerated and the destination is correct, then "
                f"raise photos.obsolete_delete_limit_percent (0 disables the "
                f"limit) if the deletions are genuinely wanted.",
            )
            return removed_paths

    for path, local_file in candidates:
        LOGGER.info(f"Removing {local_file} ...")
        path.unlink(missing_ok=True)
        removed_paths.add(local_file)

    return removed_paths
