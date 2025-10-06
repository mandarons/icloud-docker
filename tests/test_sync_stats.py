"""Test for sync_stats.py file."""

import datetime
import unittest

from src.sync_stats import (
    DriveStats,
    PhotoStats,
    SyncSummary,
    format_bytes,
    format_duration,
)


class TestSyncStats(unittest.TestCase):
    """Tests class for sync_stats.py file."""

    def test_drive_stats_has_activity(self):
        """Test DriveStats.has_activity() method."""
        # No activity
        stats = DriveStats()
        self.assertFalse(stats.has_activity())

        # Has downloaded files
        stats = DriveStats(files_downloaded=5)
        self.assertTrue(stats.has_activity())

        # Has skipped files
        stats = DriveStats(files_skipped=10)
        self.assertTrue(stats.has_activity())

        # Has removed files
        stats = DriveStats(files_removed=2)
        self.assertTrue(stats.has_activity())

    def test_drive_stats_has_errors(self):
        """Test DriveStats.has_errors() method."""
        # No errors
        stats = DriveStats()
        self.assertFalse(stats.has_errors())

        # Has errors
        stats = DriveStats(errors=["error1", "error2"])
        self.assertTrue(stats.has_errors())

    def test_photo_stats_has_activity(self):
        """Test PhotoStats.has_activity() method."""
        # No activity
        stats = PhotoStats()
        self.assertFalse(stats.has_activity())

        # Has downloaded photos
        stats = PhotoStats(photos_downloaded=5)
        self.assertTrue(stats.has_activity())

        # Has hardlinked photos
        stats = PhotoStats(photos_hardlinked=10)
        self.assertTrue(stats.has_activity())

        # Has skipped photos
        stats = PhotoStats(photos_skipped=2)
        self.assertTrue(stats.has_activity())

    def test_photo_stats_has_errors(self):
        """Test PhotoStats.has_errors() method."""
        # No errors
        stats = PhotoStats()
        self.assertFalse(stats.has_errors())

        # Has errors
        stats = PhotoStats(errors=["error1", "error2"])
        self.assertTrue(stats.has_errors())

    def test_sync_summary_has_activity(self):
        """Test SyncSummary.has_activity() method."""
        # No activity
        summary = SyncSummary()
        self.assertFalse(summary.has_activity())

        # Drive has activity
        summary = SyncSummary(drive_stats=DriveStats(files_downloaded=5))
        self.assertTrue(summary.has_activity())

        # Photos has activity
        summary = SyncSummary(photo_stats=PhotoStats(photos_downloaded=3))
        self.assertTrue(summary.has_activity())

        # Both have activity
        summary = SyncSummary(
            drive_stats=DriveStats(files_downloaded=5),
            photo_stats=PhotoStats(photos_downloaded=3),
        )
        self.assertTrue(summary.has_activity())

    def test_sync_summary_has_errors(self):
        """Test SyncSummary.has_errors() method."""
        # No errors
        summary = SyncSummary()
        self.assertFalse(summary.has_errors())

        # Drive has errors
        summary = SyncSummary(drive_stats=DriveStats(errors=["error"]))
        self.assertTrue(summary.has_errors())

        # Photos has errors
        summary = SyncSummary(photo_stats=PhotoStats(errors=["error"]))
        self.assertTrue(summary.has_errors())

        # Both have errors
        summary = SyncSummary(
            drive_stats=DriveStats(errors=["error1"]),
            photo_stats=PhotoStats(errors=["error2"]),
        )
        self.assertTrue(summary.has_errors())

    def test_sync_summary_total_duration(self):
        """Test SyncSummary.total_duration_seconds() method."""
        # No end time
        summary = SyncSummary()
        self.assertEqual(summary.total_duration_seconds(), 0.0)

        # With end time
        start = datetime.datetime(2023, 1, 1, 10, 0, 0)
        end = datetime.datetime(2023, 1, 1, 10, 5, 30)
        summary = SyncSummary(sync_start_time=start, sync_end_time=end)
        self.assertEqual(summary.total_duration_seconds(), 330.0)  # 5.5 minutes

    def test_format_bytes(self):
        """Test format_bytes() function."""
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(500), "500.0 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(1536), "1.5 KB")
        self.assertEqual(format_bytes(1048576), "1.0 MB")
        self.assertEqual(format_bytes(1572864), "1.5 MB")
        self.assertEqual(format_bytes(1073741824), "1.0 GB")
        self.assertEqual(format_bytes(2415919104), "2.2 GB")

    def test_format_duration(self):
        """Test format_duration() function."""
        self.assertEqual(format_duration(0), "0s")
        self.assertEqual(format_duration(30), "30s")
        self.assertEqual(format_duration(59), "59s")
        self.assertEqual(format_duration(60), "1m 0s")
        self.assertEqual(format_duration(90), "1m 30s")
        self.assertEqual(format_duration(272), "4m 32s")
        self.assertEqual(format_duration(3600), "1h 0m")
        self.assertEqual(format_duration(4500), "1h 15m")
        self.assertEqual(format_duration(7265), "2h 1m")


if __name__ == "__main__":
    unittest.main()
