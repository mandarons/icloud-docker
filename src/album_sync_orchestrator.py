"""Album synchronization orchestration module.

This module contains the main album sync orchestration logic
that coordinates photo filtering, download collection, and parallel execution.
"""

___author___ = "Mandar Patil <mandarons@pm.me>"

import os
from typing import Any

from src import config_parser, get_logger
from src.hardlink_registry import HardlinkRegistry
from src.photo_download_manager import (
    DownloadTaskInfo,
    collect_download_task,
    execute_parallel_downloads,
)
from src.photo_filter_utils import is_photo_wanted
from src.photo_path_utils import normalize_file_path

LOGGER = get_logger()

# Default chunk size for streaming photo enumeration. Picked to keep peak
# RSS bounded at ~10–20 MB of DownloadTaskInfo objects per chunk on
# typical iCloud libraries while still giving execute_parallel_downloads
# enough work to amortize HTTP connection setup. Users can override via
# ``photos.enumeration_chunk_size`` in config.yaml.
DEFAULT_ENUMERATION_CHUNK_SIZE = 1000


def sync_album_photos(
    album,
    destination_path: str,
    file_sizes: list[str],
    extensions: list[str] | None = None,
    files: set[str] | None = None,
    folder_format: str | None = None,
    hardlink_registry: HardlinkRegistry | None = None,
    config=None,
) -> tuple[int, int] | None:
    """Sync photos from given album.

    This function orchestrates the synchronization of a single album by:
    1. Creating the destination directory
    2. Collecting download tasks for wanted photos
    3. Executing downloads in parallel
    4. Recursively syncing subalbums

    Args:
        album: Album object from iCloudPy
        destination_path: Path where photos should be saved
        file_sizes: List of file size variants to download
        extensions: List of allowed file extensions (None = all allowed)
        files: Set to track downloaded files
        folder_format: strftime format string for folder organization
        hardlink_registry: Registry for tracking downloaded files for hardlinks
        config: Configuration dictionary

    Returns:
        Tuple of (total_successful, total_failed) download counts, or None on invalid input
    """
    if album is None or destination_path is None or file_sizes is None:
        return None

    # Create destination directory with normalized path
    normalized_destination = normalize_file_path(destination_path)
    os.makedirs(normalized_destination, exist_ok=True)
    LOGGER.info(f"Syncing {album.title}")

    # Stream the album in fixed-size chunks: collect → download →
    # release → next chunk. Memory is bounded by chunk_size × per-task
    # size (~10 MB at chunk=1000) instead of len(album) × per-task size
    # (which OOM-kills containers on ~100K+ libraries: empirically a
    # 111K-photo library peaks at ~4 GB RSS without chunking, kernel-
    # confirmed via cgroup OOM at the 4 GB cap).
    chunk_size = config_parser.get_photos_enumeration_chunk_size(config=config)
    total_successful, total_failed = _collect_and_execute_album_in_chunks(
        album,
        normalized_destination,
        file_sizes,
        extensions,
        files,
        folder_format,
        hardlink_registry,
        config,
        chunk_size=chunk_size,
    )

    # Recursively sync subalbums and aggregate counts
    sub_successful, sub_failed = _sync_subalbums(
        album,
        normalized_destination,
        file_sizes,
        extensions,
        files,
        folder_format,
        hardlink_registry,
        config,
    )
    total_successful += sub_successful
    total_failed += sub_failed

    return total_successful, total_failed


def _collect_photo_download_tasks(
    photo: Any,
    destination_path: str,
    file_sizes: list[str],
    extensions: list[str] | None,
    files: set[str] | None,
    folder_format: str | None,
    hardlink_registry: HardlinkRegistry | None,
) -> list[DownloadTaskInfo]:
    """Collect download tasks for a single photo, handling errors gracefully.

    Wraps per-photo processing so that exceptions (e.g. binascii.Error from
    iCloudPy's base64-encoded filename decoding) are caught at the photo level
    rather than inside the album iteration loop (avoids PERF203).

    Args:
        photo: Photo object from iCloudPy
        destination_path: Path where photos should be saved
        file_sizes: List of file size variants to download
        extensions: List of allowed file extensions
        files: Set to track downloaded files
        folder_format: strftime format string for folder organization
        hardlink_registry: Registry for tracking downloaded files

    Returns:
        List of download tasks for this photo (empty on error or if unwanted)
    """
    try:
        if not is_photo_wanted(photo, extensions):
            LOGGER.debug(f"Skipping the unwanted photo {photo.filename}.")
            return []
        tasks: list[DownloadTaskInfo] = []
        for file_size in file_sizes:
            download_info = collect_download_task(
                photo,
                file_size,
                destination_path,
                files,
                folder_format,
                hardlink_registry,
            )
            if download_info:
                tasks.append(download_info)
        return tasks
    except Exception as e:
        try:
            photo_id = photo.id
        except Exception:
            photo_id = "<unknown>"
        LOGGER.warning(
            f"Error processing photo (id: {photo_id}), skipping: {type(e).__name__}: {e!s}"
        )
        return []


def _collect_album_download_tasks(
    album,
    destination_path: str,
    file_sizes: list[str],
    extensions: list[str] | None,
    files: set[str] | None,
    folder_format: str | None,
    hardlink_registry: HardlinkRegistry | None,
) -> list:
    """Collect download tasks for all photos in an album.

    .. deprecated::
        Materializes the full task list — unbounded memory on large
        libraries. Kept as a thin wrapper for test backward-compat
        only. Production code path goes through
        ``_collect_and_execute_album_in_chunks`` which streams instead.

    Args:
        album: Album object from iCloudPy
        destination_path: Path where photos should be saved
        file_sizes: List of file size variants to download
        extensions: List of allowed file extensions
        files: Set to track downloaded files
        folder_format: strftime format string for folder organization
        hardlink_registry: Registry for tracking downloaded files

    Returns:
        List of download tasks to execute
    """
    download_tasks = []

    for photo in album:
        download_tasks.extend(
            _collect_photo_download_tasks(
                photo,
                destination_path,
                file_sizes,
                extensions,
                files,
                folder_format,
                hardlink_registry,
            ),
        )

    return download_tasks


def _collect_and_execute_album_in_chunks(
    album,
    destination_path: str,
    file_sizes: list[str],
    extensions: list[str] | None,
    files: set[str] | None,
    folder_format: str | None,
    hardlink_registry: HardlinkRegistry | None,
    config,
    chunk_size: int = DEFAULT_ENUMERATION_CHUNK_SIZE,
) -> tuple[int, int]:
    """Stream album → fixed-size chunks → download → release.

    Buffers up to ``chunk_size`` download tasks, then drains them via
    ``execute_parallel_downloads`` and clears the buffer before
    collecting the next chunk. Memory is bounded by chunk_size, not by
    len(album). Semantically equivalent to building the full task list
    and downloading once — same total counts, same per-photo
    side-effects — but resident-set stays flat instead of growing
    monotonically through enumeration.

    Args:
        album: Album object from iCloudPy
        destination_path: Path where photos should be saved
        file_sizes: List of file size variants to download
        extensions: List of allowed file extensions
        files: Set to track downloaded files
        folder_format: strftime format string for folder organization
        hardlink_registry: Registry for tracking downloaded files
        config: Configuration dictionary (passed through to
            ``execute_parallel_downloads`` for per-album thread count)
        chunk_size: Tasks to buffer before draining. Smaller = lower
            peak memory but more per-chunk HTTP setup overhead.

    Returns:
        Tuple of (total_successful, total_failed) summed across chunks.
    """
    if chunk_size <= 0:
        # Degenerate config; fall back to default rather than refusing
        # to sync. Logging is at INFO so operators see the fallback.
        LOGGER.info(
            f"Invalid photos.enumeration_chunk_size={chunk_size!r}; "
            f"using default {DEFAULT_ENUMERATION_CHUNK_SIZE}.",
        )
        chunk_size = DEFAULT_ENUMERATION_CHUNK_SIZE

    buffer: list[DownloadTaskInfo] = []
    total_successful = 0
    total_failed = 0

    def _drain():
        nonlocal total_successful, total_failed, buffer
        if not buffer:
            return
        succ, fail = execute_parallel_downloads(buffer, config)
        total_successful += succ
        total_failed += fail
        # Explicit reassign-to-empty so the chunk's task objects (and
        # the photo references they hold) become collectable as soon
        # as the parallel-download call returns.
        buffer = []

    for photo in album:
        buffer.extend(
            _collect_photo_download_tasks(
                photo,
                destination_path,
                file_sizes,
                extensions,
                files,
                folder_format,
                hardlink_registry,
            ),
        )
        if len(buffer) >= chunk_size:
            _drain()

    _drain()  # final partial chunk

    return total_successful, total_failed


def _sync_subalbums(
    album,
    destination_path: str,
    file_sizes: list[str],
    extensions: list[str] | None,
    files: set[str] | None,
    folder_format: str | None,
    hardlink_registry: HardlinkRegistry | None,
    config,
) -> tuple[int, int]:
    """Recursively sync all subalbums.

    Args:
        album: Album object from iCloudPy
        destination_path: Base path where subalbums should be created
        file_sizes: List of file size variants to download
        extensions: List of allowed file extensions
        files: Set to track downloaded files
        folder_format: strftime format string for folder organization
        hardlink_registry: Registry for tracking downloaded files
        config: Configuration dictionary

    Returns:
        Tuple of (total_successful, total_failed) aggregated across all subalbums
    """
    total_successful, total_failed = 0, 0
    for subalbum in album.subalbums:
        result = sync_album_photos(
            album.subalbums[subalbum],
            os.path.join(destination_path, subalbum),
            file_sizes,
            extensions,
            files,
            folder_format,
            hardlink_registry,
            config,
        )
        if result is not None:
            sub_successful, sub_failed = result
            total_successful += sub_successful
            total_failed += sub_failed
    return total_successful, total_failed
