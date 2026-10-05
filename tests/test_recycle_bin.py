"""Tests for the recycle bin used by obsolete-file cleanup."""

import datetime
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from src import config_parser, drive_cleanup, photo_cleanup_utils, recycle_bin

TODAY = datetime.date(2026, 10, 4)


def _write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(text)


class _BinTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.photos = os.path.join(self.root, "photos")
        os.makedirs(self.photos)

    def _bin(self, service="photos", retention_days=None):
        return recycle_bin.RecycleBin(
            self.root, service, retention_days=retention_days, today=TODAY,
        )

    def _in_bin(self, service, *parts):
        return os.path.join(
            self.root, "Recently Deleted", service, TODAY.isoformat(), *parts,
        )


class TestRecycleBin(_BinTestCase):
    def test_discard_keeps_the_path_relative_to_the_destination(self):
        old = os.path.join(self.photos, "2010", "08", "IMG_1.MOV")
        _write(old, "video")

        moved = self._bin().discard(old, self.photos)

        self.assertEqual(moved, self._in_bin("photos", "2010", "08", "IMG_1.MOV"))
        self.assertEqual(Path(moved).read_text(), "video")
        self.assertFalse(os.path.exists(old))

    def test_the_same_path_twice_in_a_day_keeps_both(self):
        bin_ = self._bin()
        path = os.path.join(self.photos, "a.jpg")
        _write(path, "first")
        first = bin_.discard(path, self.photos)
        _write(path, "second")
        second = bin_.discard(path, self.photos)

        self.assertEqual(second, first + " (2)")
        self.assertEqual(Path(first).read_text(), "first")
        self.assertEqual(Path(second).read_text(), "second")

    def test_contains_covers_every_service_bin_but_not_the_library(self):
        bin_ = self._bin()
        self.assertTrue(bin_.contains(os.path.join(self.root, "Recently Deleted")))
        self.assertTrue(
            bin_.contains(os.path.join(self.root, "Recently Deleted", "drive", "x")),
        )
        self.assertFalse(
            bin_.contains(os.path.join(self.root, "Recently Deleted Photos", "x")),
        )
        self.assertFalse(bin_.contains(os.path.join(self.photos, "a.jpg")))

    def test_purge_deletes_only_day_folders_past_retention(self):
        bin_ = self._bin(retention_days=30)
        base = os.path.join(self.root, "Recently Deleted", "photos")
        for day in ("2026-09-01", "2026-09-04", "2026-09-05", "notes"):
            _write(os.path.join(base, day, "f"))

        # Thirty days back from 2026-10-04 is 2026-09-04, still kept.
        self.assertEqual(bin_.purge(), 1)
        self.assertEqual(sorted(os.listdir(base)), ["2026-09-04", "2026-09-05", "notes"])

    def test_purge_keeps_everything_without_retention(self):
        _write(os.path.join(self.root, "Recently Deleted", "photos", "2000-01-01", "f"))
        self.assertEqual(self._bin().purge(), 0)

    def test_purge_with_no_bin_yet(self):
        self.assertEqual(self._bin(retention_days=1).purge(), 0)

    def test_default_day_is_today(self):
        self.assertEqual(
            recycle_bin.RecycleBin(self.root, "drive").today, datetime.date.today(),
        )


class TestRecycleBinConfig(unittest.TestCase):
    def test_off_by_default(self):
        self.assertFalse(config_parser.get_recycle_bin_enabled({"app": {}}))
        self.assertIsNone(recycle_bin.from_config({"app": {}}, "photos"))
        self.assertIsNone(recycle_bin.from_config(None, "photos"))

    def test_enabled_builds_the_service_bin_under_root(self):
        config = {
            "app": {
                "root": "/icloud",
                "recycle_bin": {"enabled": True, "retention_days": 30},
            },
        }
        bin_ = recycle_bin.from_config(config, "drive")
        self.assertEqual(bin_.path, os.path.abspath("/icloud/Recently Deleted/drive"))
        self.assertEqual(bin_.retention_days, 30)

    def test_retention_must_be_a_positive_whole_number(self):
        for value in (0, -3, "30", 1.5, True):
            with self.subTest(value=value), self.assertLogs(level="WARNING"):
                config = {
                    "app": {"recycle_bin": {"enabled": True, "retention_days": value}},
                }
                self.assertIsNone(config_parser.get_recycle_bin_retention_days(config))
        self.assertIsNone(
            config_parser.get_recycle_bin_retention_days({"app": {"recycle_bin": {}}}),
        )


class TestPhotoCleanupUsesTheBin(_BinTestCase):
    def setUp(self):
        super().setUp()
        self.tracked = set()
        for name in ("keep1.jpg", "keep2.jpg", "keep3.jpg", "keep4.jpg"):
            path = os.path.join(self.photos, name)
            _write(path)
            self.tracked.add(os.path.abspath(path))

    def test_an_obsolete_photo_is_moved_not_deleted(self):
        gone = os.path.join(self.photos, "2010", "IMG_9.MOV")
        _write(gone, "video")

        removed = photo_cleanup_utils.remove_obsolete_files(
            self.photos, self.tracked, recycle_bin=self._bin(),
        )

        self.assertEqual(removed, {os.path.abspath(gone)})
        self.assertEqual(
            Path(self._in_bin("photos", "2010", "IMG_9.MOV")).read_text(), "video",
        )

    def test_the_delete_limit_still_applies(self):
        for i in range(4):
            _write(os.path.join(self.photos, f"gone{i}.jpg"))

        removed = photo_cleanup_utils.remove_obsolete_files(
            self.photos,
            self.tracked,
            limit_percent=25,
            recycle_bin=self._bin(),
        )

        self.assertEqual(removed, set())
        self.assertFalse(os.path.exists(os.path.join(self.root, "Recently Deleted")))

    def test_a_bin_inside_the_destination_is_neither_cleaned_nor_counted(self):
        """A destination can be app.root itself, with the bin inside it."""
        day = os.path.join(self.root, "Recently Deleted", "photos", "2026-10-01")
        for i in range(20):
            _write(os.path.join(day, f"binned{i}.jpg"))
        tracked = set()
        for i in range(8):
            path = os.path.join(self.root, f"lib{i}.jpg")
            _write(path)
            tracked.add(os.path.abspath(path))
        gone = os.path.join(self.root, "gone.jpg")
        _write(gone)

        removed = photo_cleanup_utils.remove_obsolete_files(
            self.root,
            tracked | self.tracked,
            limit_percent=25,
            recycle_bin=self._bin(),
        )

        # 1 obsolete of 13 library files; counting the bin's 20 as library
        # files would not change the verdict here, but none may be removed.
        self.assertEqual(removed, {os.path.abspath(gone)})
        self.assertEqual(len(os.listdir(day)), 20)

    def test_files_in_the_bin_do_not_count_toward_the_delete_limit(self):
        """4 obsolete of 12 library files is 33%, refused at 25%; counting
        the bin's 20 would make it 4 of 32 (12.5%) and let it through."""
        day = os.path.join(self.root, "Recently Deleted", "photos", "2026-10-01")
        for i in range(20):
            _write(os.path.join(day, f"binned{i}.jpg"))
        tracked = set()
        for i in range(4):
            path = os.path.join(self.root, f"lib{i}.jpg")
            _write(path)
            tracked.add(os.path.abspath(path))
            _write(os.path.join(self.root, f"gone{i}.jpg"))

        removed = photo_cleanup_utils.remove_obsolete_files(
            self.root,
            tracked | self.tracked,
            limit_percent=25,
            recycle_bin=self._bin(),
        )

        self.assertEqual(removed, set())

    def test_retention_is_applied_even_when_nothing_is_obsolete(self):
        old_day = os.path.join(self.root, "Recently Deleted", "photos", "2026-01-01")
        _write(os.path.join(old_day, "f"))

        photo_cleanup_utils.remove_obsolete_files(
            self.photos, self.tracked, recycle_bin=self._bin(retention_days=30),
        )

        self.assertFalse(os.path.exists(old_day))


class TestDriveCleanupUsesTheBin(_BinTestCase):
    def setUp(self):
        super().setUp()
        self.drive = os.path.join(self.root, "drive")
        self.keep = os.path.join(self.drive, "Docs", "keep.txt")
        _write(self.keep)
        self.files = {
            os.path.abspath(os.path.join(self.drive, "Docs")),
            os.path.abspath(self.keep),
        }

    def test_obsolete_files_and_folders_are_moved(self):
        _write(os.path.join(self.drive, "Docs", "old.txt"), "old")
        _write(os.path.join(self.drive, "Gone", "a", "b.txt"), "b")

        removed = drive_cleanup.remove_obsolete(
            self.drive, self.files, recycle_bin=self._bin("drive"),
        )

        self.assertEqual(
            removed,
            {
                os.path.abspath(os.path.join(self.drive, "Docs", "old.txt")),
                os.path.abspath(os.path.join(self.drive, "Gone")),
            },
        )
        self.assertEqual(
            Path(self._in_bin("drive", "Docs", "old.txt")).read_text(), "old",
        )
        self.assertEqual(
            Path(self._in_bin("drive", "Gone", "a", "b.txt")).read_text(), "b",
        )
        self.assertTrue(os.path.exists(self.keep))

    def test_a_bin_inside_the_destination_is_left_alone(self):
        _write(
            os.path.join(self.root, "Recently Deleted", "drive", "2026-10-01", "x.txt"),
        )
        files = {p.replace(self.drive, self.root) for p in self.files}
        for p in files:
            _write(p) if p.endswith(".txt") else os.makedirs(p, exist_ok=True)
        files |= {os.path.abspath(self.drive), *self.files}

        drive_cleanup.remove_obsolete(self.root, files, recycle_bin=self._bin("drive"))

        self.assertTrue(
            os.path.exists(
                os.path.join(
                    self.root, "Recently Deleted", "drive", "2026-10-01", "x.txt",
                ),
            ),
        )

    def test_retention_is_applied(self):
        old_day = os.path.join(self.root, "Recently Deleted", "drive", "2026-01-01")
        _write(os.path.join(old_day, "f"))

        drive_cleanup.remove_obsolete(
            self.drive, self.files, recycle_bin=self._bin("drive", retention_days=30),
        )

        self.assertFalse(os.path.exists(old_day))

    def test_a_path_that_vanished_mid_walk_is_skipped(self):
        """rglob lists a folder before descending, so a child can name a
        path that went with its folder; it must not be moved or counted."""
        from unittest.mock import patch

        ghost = Path(self.drive, "Gone", "b.txt")
        with patch.object(Path, "rglob", return_value=[ghost]):
            removed = drive_cleanup.remove_obsolete(self.drive, self.files, recycle_bin=self._bin("drive"))

        self.assertEqual(removed, set())

    def test_without_a_bin_cleanup_still_deletes(self):
        old = os.path.join(self.drive, "Gone", "b.txt")
        _write(old)

        drive_cleanup.remove_obsolete(self.drive, self.files)

        self.assertFalse(os.path.exists(os.path.dirname(old)))
        self.assertFalse(os.path.exists(os.path.join(self.root, "Recently Deleted")))
