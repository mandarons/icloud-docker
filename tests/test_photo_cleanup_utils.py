"""Tests for photo_cleanup_utils.py module."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src import photo_cleanup_utils


class TestRemoveObsoleteFiles(unittest.TestCase):
    """Tests for remove_obsolete_files function."""

    def setUp(self):
        """Create a temporary directory with test files."""
        self.temp_dir = tempfile.mkdtemp()
        # Create some tracked files (simulating iCloud-synced photos)
        self.tracked_files = set()
        for name in ["photo1.jpg", "photo2.png", "subdir/photo3.jpg"]:
            file_path = os.path.join(self.temp_dir, name)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w") as f:
                f.write("content")
            self.tracked_files.add(str(os.path.abspath(file_path)))

    def tearDown(self):
        """Remove temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_removes_untracked_files(self):
        """Files not in tracked_files should be removed."""
        # Create an untracked file
        untracked = os.path.join(self.temp_dir, "old_photo.jpg")
        with open(untracked, "w") as f:
            f.write("old content")

        removed = photo_cleanup_utils.remove_obsolete_files(self.temp_dir, self.tracked_files)
        self.assertFalse(os.path.exists(untracked))
        self.assertIn(str(os.path.abspath(untracked)), removed)

    def test_preserves_tracked_files(self):
        """Files in tracked_files should not be removed."""
        removed = photo_cleanup_utils.remove_obsolete_files(self.temp_dir, self.tracked_files)
        for f in self.tracked_files:
            self.assertTrue(os.path.exists(f))
        self.assertEqual(len(removed), 0)

    def test_preserves_excluded_filenames(self):
        """Files in exclude_filenames should not be removed even if untracked."""
        marker = ".backup_sentinel"
        marker_path = os.path.join(self.temp_dir, marker)
        with open(marker_path, "w") as f:
            f.write("sentinel")

        untracked = os.path.join(self.temp_dir, "old_photo.jpg")
        with open(untracked, "w") as f:
            f.write("old content")

        removed = photo_cleanup_utils.remove_obsolete_files(
            self.temp_dir, self.tracked_files, exclude_filenames={marker},
        )
        # Marker should be preserved
        self.assertTrue(os.path.exists(marker_path))
        # Untracked file should be removed
        self.assertFalse(os.path.exists(untracked))
        self.assertIn(str(os.path.abspath(untracked)), removed)

    def test_excludes_multiple_filenames(self):
        """Multiple filenames in exclude_filenames should all be preserved."""
        excluded = {".backup_sentinel", ".mounted"}
        for name in excluded:
            path = os.path.join(self.temp_dir, name)
            with open(path, "w") as f:
                f.write("sentinel")

        untracked = os.path.join(self.temp_dir, "old_photo.jpg")
        with open(untracked, "w") as f:
            f.write("old content")

        photo_cleanup_utils.remove_obsolete_files(
            self.temp_dir, self.tracked_files, exclude_filenames=excluded,
        )
        for name in excluded:
            self.assertTrue(os.path.exists(os.path.join(self.temp_dir, name)))
        self.assertFalse(os.path.exists(untracked))

    def test_excluded_filenames_not_required(self):
        """Function works without exclude_filenames parameter (backward compat)."""
        untracked = os.path.join(self.temp_dir, "old_photo.jpg")
        with open(untracked, "w") as f:
            f.write("old content")

        photo_cleanup_utils.remove_obsolete_files(self.temp_dir, self.tracked_files)
        self.assertFalse(os.path.exists(untracked))

    def test_returns_empty_set_when_no_destination(self):
        """Returns empty set when destination_path is None."""
        result = photo_cleanup_utils.remove_obsolete_files(None, self.tracked_files)
        self.assertEqual(result, set())

    def test_returns_empty_set_when_no_files(self):
        """Returns empty set when tracked_files is None."""
        result = photo_cleanup_utils.remove_obsolete_files(self.temp_dir, None)
        self.assertEqual(result, set())


if __name__ == "__main__":
    unittest.main()


class TestUnremovableFiles(unittest.TestCase):
    """A file cleanup cannot remove is left and logged; the rest still go."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.paths = []
        for name in ("locked.jpg", "old.jpg"):
            path = os.path.join(self.root, name)
            with open(path, "w") as f:
                f.write("x")
            self.paths.append(os.path.abspath(path))
        self.locked, self.old = self.paths

    def _unlink(self, real=Path.unlink):
        locked = self.locked

        def unlink(path, *args, **kwargs):
            if str(path.absolute()) == locked:
                raise PermissionError(13, "Permission denied", locked)
            return real(path, *args, **kwargs)

        return unlink

    def test_photo_cleanup_carries_on(self):
        with (
            patch.object(Path, "unlink", self._unlink()),
            self.assertLogs(level="WARNING") as logs,
        ):
            removed = photo_cleanup_utils.remove_obsolete_files(self.root, set(), limit_percent=0)
        self.assertEqual(removed, {self.old})
        self.assertTrue(os.path.exists(self.locked))
        self.assertIn("Could not remove", "\n".join(logs.output))
        self.assertIn("locked.jpg", "\n".join(logs.output))

    def test_photo_cleanup_with_a_bin(self):
        bin_ = MagicMock()
        bin_.contains.return_value = False

        def discard(path, _destination):
            if path == self.locked:
                raise PermissionError(13, "Permission denied", path)

        bin_.discard.side_effect = discard
        removed = photo_cleanup_utils.remove_obsolete_files(self.root, set(), limit_percent=0, recycle_bin=bin_)
        self.assertEqual(removed, {self.old})

    def test_drive_cleanup_carries_on(self):
        from src import drive_cleanup

        folder = os.path.join(self.root, "stuck")
        os.makedirs(os.path.join(folder, "inner"))
        with (
            patch.object(Path, "unlink", self._unlink()),
            patch.object(drive_cleanup, "rmtree", side_effect=PermissionError(13, "denied", folder)),
            self.assertLogs(level="WARNING"),
        ):
            removed = drive_cleanup.remove_obsolete(self.root, set())
        self.assertEqual(removed, {self.old})
        self.assertTrue(os.path.exists(self.locked))
        self.assertTrue(os.path.isdir(folder))
