"""Live Photo .mov via explicit ``file_sizes``.

Users add ``live_video_original`` (or ``live_video_medium`` / ``live_video_thumb``)
to ``photos.filters.file_sizes`` to download the paired ``.mov`` of a Live Photo.
It flows through the normal download loop like any other version; photos that
aren't Live Photos lack the version and are skipped quietly (DEBUG, not WARNING).
"""

import logging
import unittest
from unittest.mock import MagicMock, patch

from src import config_parser, photo_download_manager
from src.album_sync_orchestrator import _collect_photo_download_tasks


def _fake_photo(filename, versions):
    """A photo stub that quacks like icloudpy.services.photos.PhotoAsset."""
    photo = MagicMock()
    photo.filename = filename
    photo.versions = versions
    photo.id = "test-photo-id"
    return photo


class TestLiveVideoFileSize(unittest.TestCase):
    """``live_video_*`` is a valid, explicit file_size."""

    def test_validate_accepts_live_video_keys(self):
        validated = config_parser.validate_file_sizes(
            ["original", "live_video_original", "live_video_medium"],
        )
        self.assertIn("live_video_original", validated)
        self.assertIn("live_video_medium", validated)

    @patch("src.album_sync_orchestrator.is_photo_wanted", return_value=True)
    @patch("src.album_sync_orchestrator.collect_download_task")
    def test_live_video_original_collected_for_live_photo(self, fake_collect, _wanted):
        """A Live Photo with live_video_original requested yields both tasks."""
        photo = _fake_photo(
            "IMG_1234.HEIC",
            {"original": {"url": "x"}, "live_video_original": {"url": "y"}},
        )
        fake_collect.side_effect = lambda *a, **kw: MagicMock(name=f"task-{a[1]}")
        tasks = _collect_photo_download_tasks(
            photo,
            destination_path="/tmp/dest",
            file_sizes=["original", "live_video_original"],
            extensions=None,
            files=set(),
            folder_format=None,
            hardlink_registry=None,
        )
        self.assertEqual(len(tasks), 2)
        called = [c.args[1] for c in fake_collect.call_args_list]
        self.assertIn("live_video_original", called)

    @patch("src.album_sync_orchestrator.is_photo_wanted", return_value=True)
    @patch("src.album_sync_orchestrator.collect_download_task")
    def test_still_photo_skips_absent_live_video(self, fake_collect, _wanted):
        """A still (no live_video_original) yields no .mov task; the still still emits."""

        def side_effect(*args, **kwargs):
            return None if args[1] == "live_video_original" else MagicMock(name=f"task-{args[1]}")

        fake_collect.side_effect = side_effect
        photo = _fake_photo("IMG_5678.HEIC", {"original": {"url": "x"}})
        tasks = _collect_photo_download_tasks(
            photo,
            destination_path="/tmp/dest",
            file_sizes=["original", "live_video_original"],
            extensions=None,
            files=set(),
            folder_format=None,
            hardlink_registry=None,
        )
        self.assertEqual(len(tasks), 1)


class TestCollectDownloadTaskMissingVersion(unittest.TestCase):
    """A version absent from photo.versions is skipped; live_video_* logs DEBUG."""

    @patch(
        "src.photo_download_manager.generate_photo_path",
        return_value="/tmp/dest/IMG.HEIC",
    )
    def test_missing_live_video_logs_debug_not_warning(self, _gp):
        photo = _fake_photo("IMG.HEIC", {"original": {"url": "x"}})
        with self.assertLogs(photo_download_manager.LOGGER, level=logging.DEBUG) as cm:
            result = photo_download_manager.collect_download_task(
                photo,
                "live_video_original",
                "/tmp/dest",
                set(),
                None,
                None,
            )
        self.assertIsNone(result)
        self.assertTrue(any("live_video_original" in line for line in cm.output))
        self.assertFalse(any("WARNING" in line for line in cm.output))

    @patch(
        "src.photo_download_manager.generate_photo_path",
        return_value="/tmp/dest/IMG.HEIC",
    )
    def test_missing_regular_size_logs_warning(self, _gp):
        photo = _fake_photo("IMG.HEIC", {"original": {"url": "x"}})
        with self.assertLogs(photo_download_manager.LOGGER, level=logging.WARNING) as cm:
            result = photo_download_manager.collect_download_task(
                photo,
                "medium",
                "/tmp/dest",
                set(),
                None,
                None,
            )
        self.assertIsNone(result)
        self.assertTrue(any("WARNING" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
