"""Tests for photo_cleanup_utils.py module."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import shutil
import tempfile
import unittest

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
