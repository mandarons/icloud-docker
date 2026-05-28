"""Live Photo .mov pair auto-append tests.

Added 2026-05-27 as part of feat/per-library-destinations-and-live-photos.

When a photo is a Live Photo (icloudpy exposes ``live_video_original`` in
``photo.versions``) and the user has requested the ``original`` file_size,
the orchestrator should automatically collect a second download task for
the paired ``.mov`` so the Live Photo round-trips intact.
"""

import unittest
from unittest.mock import MagicMock, patch

from src.album_sync_orchestrator import _collect_photo_download_tasks


def _fake_photo(filename, versions):
    """A photo stub that quacks like icloudpy.services.photos.PhotoAsset."""
    photo = MagicMock()
    photo.filename = filename
    photo.versions = versions
    photo.id = "test-photo-id"
    return photo


class TestLivePhotoPairDownload(unittest.TestCase):
    """Live Photo .mov auto-append behaviour."""

    def setUp(self):
        # Patch is_photo_wanted to always pass; we're testing task collection,
        # not the wantedness filter.
        self._wanted_patcher = patch(
            "src.album_sync_orchestrator.is_photo_wanted", return_value=True
        )
        self._wanted_patcher.start()

    def tearDown(self):
        self._wanted_patcher.stop()

    @patch("src.album_sync_orchestrator.collect_download_task")
    def test_live_photo_with_original_yields_two_tasks(self, fake_collect):
        photo = _fake_photo(
            "IMG_1234.HEIC",
            {"original": {"url": "x"}, "live_video_original": {"url": "y"}},
        )
        # Each call returns a unique MagicMock — non-None so tasks list grows
        fake_collect.side_effect = lambda *a, **kw: MagicMock(name=f"task-{a[1]}")

        tasks = _collect_photo_download_tasks(
            photo,
            destination_path="/tmp/dest",
            file_sizes=["original"],
            extensions=None,
            files=set(),
            folder_format=None,
            hardlink_registry=None,
        )

        assert len(tasks) == 2
        # Inspect which file_sizes got requested
        called_sizes = [call.args[1] for call in fake_collect.call_args_list]
        assert "original" in called_sizes
        assert "live_video_original" in called_sizes

    @patch("src.album_sync_orchestrator.collect_download_task")
    def test_still_photo_yields_only_one_task(self, fake_collect):
        photo = _fake_photo("IMG_5678.HEIC", {"original": {"url": "x"}})
        fake_collect.side_effect = lambda *a, **kw: MagicMock(name=f"task-{a[1]}")

        tasks = _collect_photo_download_tasks(
            photo,
            destination_path="/tmp/dest",
            file_sizes=["original"],
            extensions=None,
            files=set(),
            folder_format=None,
            hardlink_registry=None,
        )

        assert len(tasks) == 1
        called_sizes = [call.args[1] for call in fake_collect.call_args_list]
        assert called_sizes == ["original"]

    @patch("src.album_sync_orchestrator.collect_download_task")
    def test_live_photo_without_original_request_does_not_append_mov(
        self, fake_collect
    ):
        """If the user asked only for medium/thumb (not original), the .mov is not appended.

        The Live Photo .mov is the *original* video resource; users who explicitly
        want only smaller variants shouldn't get the original .mov bundled.
        """
        photo = _fake_photo(
            "IMG_1234.HEIC",
            {
                "medium": {"url": "m"},
                "thumb": {"url": "t"},
                "live_video_original": {"url": "y"},
            },
        )
        fake_collect.side_effect = lambda *a, **kw: MagicMock(name=f"task-{a[1]}")

        tasks = _collect_photo_download_tasks(
            photo,
            destination_path="/tmp/dest",
            file_sizes=["medium", "thumb"],
            extensions=None,
            files=set(),
            folder_format=None,
            hardlink_registry=None,
        )

        called_sizes = [call.args[1] for call in fake_collect.call_args_list]
        assert called_sizes == ["medium", "thumb"]
        assert "live_video_original" not in called_sizes

    @patch("src.album_sync_orchestrator.collect_download_task")
    def test_versions_access_failure_is_non_fatal(self, fake_collect):
        """If photo.versions raises (partial CloudKit record), still emit the still tasks."""
        photo = MagicMock()
        photo.filename = "IMG_x.HEIC"
        photo.id = "x"
        type(photo).versions = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("CloudKit broken"))
        )
        fake_collect.side_effect = lambda *a, **kw: MagicMock(name="task")

        tasks = _collect_photo_download_tasks(
            photo,
            destination_path="/tmp/dest",
            file_sizes=["original"],
            extensions=None,
            files=set(),
            folder_format=None,
            hardlink_registry=None,
        )

        # Original still task was collected; .mov path swallowed the exception
        # and did not append anything.
        assert len(tasks) == 1

    @patch("src.album_sync_orchestrator.collect_download_task")
    def test_live_video_original_with_none_collect_result_is_skipped(
        self, fake_collect
    ):
        """If collect_download_task returns None for the .mov, it's not appended."""
        photo = _fake_photo(
            "IMG_1234.HEIC",
            {"original": {"url": "x"}, "live_video_original": {"url": "y"}},
        )

        def side_effect(*args, **kwargs):
            if args[1] == "live_video_original":
                return None  # e.g. file already exists locally
            return MagicMock(name=f"task-{args[1]}")

        fake_collect.side_effect = side_effect

        tasks = _collect_photo_download_tasks(
            photo,
            destination_path="/tmp/dest",
            file_sizes=["original"],
            extensions=None,
            files=set(),
            folder_format=None,
            hardlink_registry=None,
        )

        assert len(tasks) == 1
