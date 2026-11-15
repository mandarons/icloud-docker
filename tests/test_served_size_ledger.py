"""Tests for the persisted accepted-served-size ledger."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src import served_size_ledger


class TestServedSizeLedger(unittest.TestCase):
    """Entries survive a cache reset and invalidate on either size change."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "served-sizes.json")
        served_size_ledger._entries_by_path.clear()  # noqa: SLF001 - test cache
        self.path_patch = patch.object(served_size_ledger, "_path", return_value=self.path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        served_size_ledger._entries_by_path.clear()  # noqa: SLF001 - test cache
        for name in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, name))
        os.rmdir(self.tmp)

    def test_record_then_match_survives_a_cache_reset(self):
        served_size_ledger.record("master-1", "original", 10, 8)
        self.assertTrue(served_size_ledger.matches("master-1", "original", 10, 8))
        served_size_ledger._entries_by_path.clear()  # noqa: SLF001 - reload from disk
        self.assertTrue(served_size_ledger.matches("master-1", "original", 10, 8))

    def test_either_size_change_invalidates(self):
        served_size_ledger.record("master-1", "original", 10, 8)
        self.assertFalse(served_size_ledger.matches("master-1", "original", 11, 8))
        self.assertFalse(served_size_ledger.matches("master-1", "original", 10, 9))
        self.assertFalse(served_size_ledger.matches("master-1", "full", 10, 8))
        self.assertFalse(served_size_ledger.matches("master-2", "original", 10, 8))

    def test_forget_removes_the_entry_and_is_a_no_op_otherwise(self):
        served_size_ledger.record("master-1", "original", 10, 8)
        served_size_ledger.forget("master-1", "original")
        self.assertFalse(served_size_ledger.matches("master-1", "original", 10, 8))
        # Unknown key: nothing to save, no raise.
        served_size_ledger.forget("master-1", "original")

    def test_corrupt_json_is_treated_as_empty(self):
        with open(self.path, "w") as f:
            f.write("{not json")
        with patch.object(served_size_ledger.LOGGER, "warning") as warning:
            self.assertFalse(served_size_ledger.matches("master-1", "original", 10, 8))
        warning.assert_called_once()

    def test_non_dict_json_is_treated_as_empty(self):
        with open(self.path, "w") as f:
            json.dump([], f)
        self.assertFalse(served_size_ledger.matches("master-1", "original", 10, 8))

    def test_unreadable_file_is_treated_as_empty(self):
        with (
            patch("builtins.open", side_effect=OSError("denied")),
            patch.object(served_size_ledger.LOGGER, "warning") as warning,
        ):
            self.assertFalse(served_size_ledger.matches("master-1", "original", 10, 8))
        warning.assert_called_once()

    def test_save_failure_is_logged_and_does_not_raise(self):
        with (
            patch("builtins.open", side_effect=OSError("disk full")),
            patch("os.unlink", side_effect=OSError("gone")),
            patch.object(served_size_ledger.LOGGER, "warning") as warning,
        ):
            served_size_ledger.record("master-1", "original", 10, 8)
        self.assertGreaterEqual(warning.call_count, 1)

    def test_saved_file_is_valid_json(self):
        served_size_ledger.record("master-1", "original", 10, 8)
        with open(self.path) as f:
            data = json.load(f)
        self.assertEqual(data["master-1|original"], {"declared": 10, "served": 8})


if __name__ == "__main__":
    unittest.main()
