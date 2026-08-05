"""Tests for ``src.web_signals`` — cross-thread signalling between the
embedded web UI and the sync loop.

Covers force-sync sentinels, the last-sync-state JSON, and the
relative-time formatter the dashboard uses for "5 min ago" labels.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import json
import os
import tempfile
import unittest
from unittest.mock import patch

import tests  # noqa: F401  — env setup
from src import web_signals


class TestConfigDirResolution(unittest.TestCase):
    """``_config_dir`` derives from DEFAULT_COOKIE_DIRECTORY by stripping
    the trailing `session_data` component — same logic the keyring
    redirect uses, so dev hosts without /config still resolve to a
    real writable tempdir."""

    def test_strips_session_data_from_cookie_dir(self):
        from src import DEFAULT_COOKIE_DIRECTORY

        expected_parent = os.path.dirname(DEFAULT_COOKIE_DIRECTORY) or "/config"
        self.assertEqual(web_signals._config_dir(), expected_parent)  # noqa: SLF001


class TestForceSyncSentinels(unittest.TestCase):
    """``request_force_sync`` / ``pending_force_syncs`` / ``consume_force_sync``."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._patcher = patch.object(web_signals, "_config_dir", return_value=self.tmp)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_request_rejects_unknown_service(self):
        """Only `drive` / `photos` are valid — anything else is a no-op."""
        self.assertFalse(web_signals.request_force_sync("calendar"))

    def test_request_writes_sentinel_for_valid_service(self):
        self.assertTrue(web_signals.request_force_sync("drive"))
        self.assertTrue(
            os.path.isfile(os.path.join(self.tmp, ".force-sync-drive")),
        )

    def test_request_idempotent_re_tap_is_ok(self):
        """Re-tapping while a previous request is still queued returns
        True (the prior sentinel is still in place)."""
        self.assertTrue(web_signals.request_force_sync("photos"))
        self.assertTrue(web_signals.request_force_sync("photos"))

    def test_request_oserror_returns_false(self):
        """A write failure (FS perms, disk full) logs a warning and
        returns False — the dashboard renders that as "couldn't queue"."""
        with patch("builtins.open", side_effect=OSError("disk full")):
            self.assertFalse(web_signals.request_force_sync("drive"))

    def test_pending_lists_only_queued_services(self):
        """``pending_force_syncs`` returns the queued service names."""
        web_signals.request_force_sync("drive")
        self.assertEqual(web_signals.pending_force_syncs(), ["drive"])
        web_signals.request_force_sync("photos")
        self.assertEqual(
            sorted(web_signals.pending_force_syncs()),
            ["drive", "photos"],
        )

    def test_consume_rejects_unknown_service(self):
        self.assertFalse(web_signals.consume_force_sync("calendar"))

    def test_consume_returns_false_when_no_sentinel(self):
        """Sync loop calls this on every iteration — absence is the
        common case, not an error."""
        self.assertFalse(web_signals.consume_force_sync("drive"))

    def test_consume_returns_true_and_deletes_sentinel(self):
        web_signals.request_force_sync("drive")
        self.assertTrue(web_signals.consume_force_sync("drive"))
        # Second call returns False — sentinel is gone.
        self.assertFalse(web_signals.consume_force_sync("drive"))

    def test_consume_oserror_returns_false(self):
        """OS errors other than FileNotFoundError surface as False
        (failed to consume — leave for next iteration)."""
        web_signals.request_force_sync("photos")
        with patch("os.unlink", side_effect=OSError("perms")):
            self.assertFalse(web_signals.consume_force_sync("photos"))


class TestSyncStatePersistence(unittest.TestCase):
    """``record_sync_completion`` + ``get_sync_state`` + ``_load_state`` /
    ``_save_state`` round-trip through the on-disk JSON file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._patcher = patch.object(web_signals, "_config_dir", return_value=self.tmp)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_record_ignores_unknown_service(self):
        web_signals.record_sync_completion("calendar", files_downloaded=1)
        # No JSON file should exist
        self.assertFalse(
            os.path.isfile(os.path.join(self.tmp, ".last-sync-state.json")),
        )

    def test_record_persists_all_provided_fields(self):
        web_signals.record_sync_completion(
            "drive",
            files_downloaded=10,
            files_skipped=5,
            files_removed=1,
            errors=0,
            duration_seconds=12.5,
        )
        state = web_signals.get_sync_state("drive")
        self.assertEqual(state["files_downloaded"], 10)
        self.assertEqual(state["files_skipped"], 5)
        self.assertEqual(state["files_removed"], 1)
        self.assertEqual(state["errors"], 0)
        self.assertAlmostEqual(state["duration_seconds"], 12.5)
        self.assertIn("completed_at", state)

    def test_record_none_fields_preserve_prior_value(self):
        """Passing None on subsequent record() doesn't wipe the prior
        counter — useful when one path knows downloaded but not skipped."""
        web_signals.record_sync_completion(
            "photos",
            files_downloaded=100,
            errors=2,
        )
        # Second call: only update files_downloaded
        web_signals.record_sync_completion("photos", files_downloaded=150)
        state = web_signals.get_sync_state("photos")
        self.assertEqual(state["files_downloaded"], 150)
        self.assertEqual(state["errors"], 2)  # preserved from first call

    def test_get_state_unknown_service_returns_empty(self):
        self.assertEqual(web_signals.get_sync_state("calendar"), {})

    def test_get_state_missing_file_returns_empty(self):
        self.assertEqual(web_signals.get_sync_state("drive"), {})

    def test_load_state_corrupt_json_logged_and_returns_empty(self):
        """A corrupt state JSON shouldn't crash the dashboard — log
        and treat as empty."""
        path = os.path.join(self.tmp, ".last-sync-state.json")
        with open(path, "w") as f:
            f.write("{not valid json")
        self.assertEqual(web_signals.get_sync_state("drive"), {})

    def test_load_state_non_dict_top_level_returns_empty(self):
        """Defensive: if someone writes a JSON list at the path,
        treat as empty rather than crash callers."""
        path = os.path.join(self.tmp, ".last-sync-state.json")
        with open(path, "w") as f:
            json.dump(["not", "a", "dict"], f)
        self.assertEqual(web_signals.get_sync_state("drive"), {})

    def test_load_state_oserror_returns_empty(self):
        path = os.path.join(self.tmp, ".last-sync-state.json")
        with open(path, "w") as f:
            f.write("{}")
        with patch("builtins.open", side_effect=OSError("perms")):
            self.assertEqual(web_signals.get_sync_state("drive"), {})

    def test_save_state_oserror_logged_and_silent(self):
        """A failed save mustn't kill the sync loop — log and continue."""
        with patch("os.rename", side_effect=OSError("perms")):
            # Should not raise.
            web_signals.record_sync_completion("drive", files_downloaded=1)

    def test_save_state_temp_cleanup_oserror_swallowed(self):
        """If save fails AND the tmp-file cleanup also fails, the
        exception still doesn't propagate."""
        with patch("os.rename", side_effect=OSError("rename perms")), patch(
            "os.unlink",
            side_effect=OSError("unlink perms"),
        ):
            web_signals.record_sync_completion("drive", files_downloaded=1)


class TestFormatRelativeTime(unittest.TestCase):
    """Compact relative-time formatter (Just now / N sec ago / N min ago /
    N h ago / N d ago)."""

    def test_empty_or_zero_returns_empty_string(self):
        self.assertEqual(web_signals.format_relative_time(0), "")
        self.assertEqual(web_signals.format_relative_time(None), "")

    def test_just_now_under_30_seconds(self):
        self.assertEqual(
            web_signals.format_relative_time(101.0, now=1.0 + 120.0),
            "Just now",
        )

    def test_seconds_30_to_120(self):
        self.assertEqual(
            web_signals.format_relative_time(1.0, now=1.0 + 60.0),
            "60 sec ago",
        )

    def test_minutes_120_to_3600(self):
        self.assertEqual(
            web_signals.format_relative_time(1.0, now=1.0 + 600.0),
            "10 min ago",
        )

    def test_hours_3600_to_86400(self):
        self.assertEqual(
            web_signals.format_relative_time(1.0, now=1.0 + 7200.0),
            "2 h ago",
        )

    def test_days_over_86400(self):
        self.assertEqual(
            web_signals.format_relative_time(1.0, now=1.0 + 86400.0 * 3),
            "3 d ago",
        )

    def test_future_timestamp_clamped_to_just_now(self):
        """Defensive: clock skew can leave the timestamp slightly in the
        future. Clamp delta to 0 instead of returning a negative-sec
        string."""
        self.assertEqual(
            web_signals.format_relative_time(201.0, now=1.0 + 100.0),
            "Just now",
        )

    def test_now_default_uses_wall_clock(self):
        """When `now` isn't passed, `time.time()` is consulted — the
        result should still be a relative-time string."""
        import time as time_module

        # Use a timestamp 600 seconds in the past
        result = web_signals.format_relative_time(time_module.time() - 600)
        # 10 min ago, give or take rounding
        self.assertIn("min ago", result)


if __name__ == "__main__":
    unittest.main()
