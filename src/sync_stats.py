"""Sync statistics module for tracking sync operations and generating summaries."""

import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DriveStats:
    """Statistics for drive synchronization operations.

    Tracks download counts, sizes, durations, and other metrics
    for drive sync operations.
    """

    files_downloaded: int = 0
    files_skipped: int = 0
    files_removed: int = 0
    bytes_downloaded: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def has_activity(self) -> bool:
        """Check if there was any sync activity.

        Returns:
            True if any files were downloaded, skipped, or removed
        """
        return self.files_downloaded > 0 or self.files_skipped > 0 or self.files_removed > 0

    def has_errors(self) -> bool:
        """Check if there were any errors.

        Returns:
            True if errors list is not empty
        """
        return len(self.errors) > 0


@dataclass
class PhotoStats:
    """Statistics for photo synchronization operations.

    Tracks download counts, hardlink usage, sizes, durations,
    and other metrics for photo sync operations.
    """

    photos_downloaded: int = 0
    photos_hardlinked: int = 0
    photos_skipped: int = 0
    bytes_downloaded: int = 0
    bytes_saved_by_hardlinks: int = 0
    albums_synced: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    def has_activity(self) -> bool:
        """Check if there was any sync activity.

        Returns:
            True if any photos were downloaded, hardlinked, or skipped
        """
        return self.photos_downloaded > 0 or self.photos_hardlinked > 0 or self.photos_skipped > 0

    def has_errors(self) -> bool:
        """Check if there were any errors.

        Returns:
            True if errors list is not empty
        """
        return len(self.errors) > 0


@dataclass
class SyncSummary:
    """Overall synchronization summary combining drive and photo stats.

    Contains statistics for both drive and photo syncs, along with
    timing information for the overall sync operation.
    """

    drive_stats: Optional[DriveStats] = None
    photo_stats: Optional[PhotoStats] = None
    sync_start_time: datetime.datetime = field(default_factory=datetime.datetime.now)
    sync_end_time: Optional[datetime.datetime] = None

    def has_activity(self) -> bool:
        """Check if there was any sync activity overall.

        Returns:
            True if either drive or photos had activity
        """
        drive_activity = self.drive_stats.has_activity() if self.drive_stats else False
        photo_activity = self.photo_stats.has_activity() if self.photo_stats else False
        return drive_activity or photo_activity

    def has_errors(self) -> bool:
        """Check if there were any errors in the sync.

        Returns:
            True if either drive or photos had errors
        """
        drive_errors = self.drive_stats.has_errors() if self.drive_stats else False
        photo_errors = self.photo_stats.has_errors() if self.photo_stats else False
        return drive_errors or photo_errors

    def total_duration_seconds(self) -> float:
        """Calculate total sync duration.

        Returns:
            Total duration in seconds
        """
        if self.sync_end_time:
            return (self.sync_end_time - self.sync_start_time).total_seconds()
        return 0.0


def format_bytes(bytes_count: int) -> str:
    """Format byte count as human-readable string.

    Args:
        bytes_count: Number of bytes

    Returns:
        Formatted string (e.g., "1.5 GB", "234 MB")
    """
    if bytes_count == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(bytes_count)

    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    return f"{size:.1f} {units[unit_index]}"


def format_duration(seconds: float) -> str:
    """Format duration as human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string (e.g., "4m 32s", "1h 15m")
    """
    if seconds < 60:
        return f"{int(seconds)}s"

    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)

    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"

    hours = minutes // 60
    remaining_minutes = minutes % 60
    return f"{hours}h {remaining_minutes}m"
