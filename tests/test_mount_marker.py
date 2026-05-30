"""Tests for the mount-marker failsafe (``photos.require_mount_marker`` /
``drive.require_mount_marker`` / ``app.mount_marker_filename``)."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import logging
import os
import tempfile
import unittest

from src import config_parser, sync


class TestMountMarkerConfigHelpers(unittest.TestCase):
    """Defaults + read-through behaviour for the three config helpers."""

    def test_get_drive_require_mount_marker_default_false(self):
        """Default is False so existing installs see no behaviour change."""
        self.assertFalse(config_parser.get_drive_require_mount_marker(config={}))
        self.assertFalse(
            config_parser.get_drive_require_mount_marker(config={"drive": {}}),
        )

    def test_get_drive_require_mount_marker_true_when_set(self):
        """Returns True when explicitly enabled."""
        self.assertTrue(
            config_parser.get_drive_require_mount_marker(
                config={"drive": {"require_mount_marker": True}},
            ),
        )

    def test_get_photos_require_mount_marker_default_false(self):
        """Default is False so existing installs see no behaviour change."""
        self.assertFalse(config_parser.get_photos_require_mount_marker(config={}))
        self.assertFalse(
            config_parser.get_photos_require_mount_marker(config={"photos": {}}),
        )

    def test_get_photos_require_mount_marker_true_when_set(self):
        """Returns True when explicitly enabled."""
        self.assertTrue(
            config_parser.get_photos_require_mount_marker(
                config={"photos": {"require_mount_marker": True}},
            ),
        )

    def test_get_mount_marker_filename_default(self):
        """Default marker filename is ``.mounted`` (matches boredazfcuk convention)."""
        self.assertEqual(config_parser.get_mount_marker_filename(config={}), ".mounted")
        self.assertEqual(
            config_parser.get_mount_marker_filename(config={"app": {}}),
            ".mounted",
        )

    def test_get_mount_marker_filename_when_configured(self):
        """Returns the configured filename when ``app.mount_marker_filename`` is set."""
        self.assertEqual(
            config_parser.get_mount_marker_filename(
                config={"app": {"mount_marker_filename": ".icloud-ok"}},
            ),
            ".icloud-ok",
        )


class TestCheckMountMarker(unittest.TestCase):
    """Behaviour of ``sync._check_mount_marker``."""

    def setUp(self):
        """Create an isolated tempdir per test."""
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        """Remove the tempdir."""
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_true_when_not_required(self):
        """No marker file means no-op when require=False."""
        self.assertTrue(
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[self.tmp],
                marker_filename=".mounted",
                required=False,
                service_name="Drive",
            ),
        )

    def test_returns_true_when_required_and_marker_present(self):
        """Marker file present satisfies the failsafe."""
        open(os.path.join(self.tmp, ".mounted"), "w").close()
        self.assertTrue(
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[self.tmp],
                marker_filename=".mounted",
                required=True,
                service_name="Drive",
            ),
        )

    def test_returns_false_when_required_and_marker_absent(self):
        """Marker absent + required → False (caller should skip sync)."""
        self.assertFalse(
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[self.tmp],
                marker_filename=".mounted",
                required=True,
                service_name="Drive",
            ),
        )

    def test_error_logged_when_marker_missing(self):
        """Refusal is logged at ERROR level with actionable instructions."""
        with self.assertLogs(sync.LOGGER, level=logging.ERROR) as cm:
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[self.tmp],
                marker_filename=".mounted",
                required=True,
                service_name="Photos",
            )
        joined = "\n".join(cm.output)
        self.assertIn("Photos mount marker missing", joined)
        self.assertIn(os.path.join(self.tmp, ".mounted"), joined)
        self.assertIn("touch", joined)

    def test_custom_marker_filename_honoured(self):
        """``marker_filename`` parameter overrides the default."""
        open(os.path.join(self.tmp, ".icloud-ok"), "w").close()
        # Default name would fail; custom name succeeds.
        self.assertFalse(
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[self.tmp],
                marker_filename=".mounted",
                required=True,
                service_name="Drive",
            ),
        )
        self.assertTrue(
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[self.tmp],
                marker_filename=".icloud-ok",
                required=True,
                service_name="Drive",
            ),
        )

    def test_multiple_destinations_all_present(self):
        """When every destination has the marker, returns True."""
        sub1 = os.path.join(self.tmp, "personal")
        sub2 = os.path.join(self.tmp, "shared")
        os.makedirs(sub1)
        os.makedirs(sub2)
        for d in (self.tmp, sub1, sub2):
            open(os.path.join(d, ".mounted"), "w").close()
        self.assertTrue(
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[self.tmp, sub1, sub2],
                marker_filename=".mounted",
                required=True,
                service_name="Photos",
            ),
        )

    def test_multiple_destinations_one_missing_returns_false(self):
        """One missing marker among many destinations refuses the cycle."""
        sub1 = os.path.join(self.tmp, "personal")
        sub2 = os.path.join(self.tmp, "shared")
        os.makedirs(sub1)
        os.makedirs(sub2)
        # Root + personal have marker; shared does not.
        open(os.path.join(self.tmp, ".mounted"), "w").close()
        open(os.path.join(sub1, ".mounted"), "w").close()
        self.assertFalse(
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[self.tmp, sub1, sub2],
                marker_filename=".mounted",
                required=True,
                service_name="Photos",
            ),
        )

    def test_multiple_destinations_logs_every_missing(self):
        """Each missing destination is logged so user can fix them all at once."""
        sub_personal = os.path.join(self.tmp, "personal")
        sub_shared = os.path.join(self.tmp, "shared")
        os.makedirs(sub_personal)
        os.makedirs(sub_shared)
        # No markers anywhere.
        with self.assertLogs(sync.LOGGER, level=logging.ERROR) as cm:
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[self.tmp, sub_personal, sub_shared],
                marker_filename=".mounted",
                required=True,
                service_name="Photos",
            )
        joined = "\n".join(cm.output)
        self.assertIn(os.path.join(self.tmp, ".mounted"), joined)
        self.assertIn(os.path.join(sub_personal, ".mounted"), joined)
        self.assertIn(os.path.join(sub_shared, ".mounted"), joined)

    def test_nonexistent_destination_treated_as_missing(self):
        """A destination that doesn't exist on disk (failed mount creates
        nothing) still surfaces a missing-marker error rather than crashing."""
        ghost = os.path.join(self.tmp, "never-mounted")
        # Intentionally do NOT mkdir ghost.
        self.assertFalse(
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[ghost],
                marker_filename=".mounted",
                required=True,
                service_name="Photos",
            ),
        )

    def test_empty_destinations_returns_true(self):
        """Empty destination list means nothing to check — safe to proceed."""
        self.assertTrue(
            sync._check_mount_marker(  # noqa: SLF001
                destinations=[],
                marker_filename=".mounted",
                required=True,
                service_name="Drive",
            ),
        )


class TestDriveSyncSkippedWhenMarkerMissing(unittest.TestCase):
    """``_perform_drive_sync`` returns None and skips the sync cycle
    when ``drive.require_mount_marker`` is true but the marker file
    isn't present at the destination."""

    def setUp(self):
        """Tempdir without any marker file."""
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        """Remove the tempdir."""
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_drive_sync_returns_none_when_marker_missing(self):
        """The Drive marker-missing branch sets the early return that
        keeps the countdown from advancing. Without this test the early
        return is unexecuted code."""
        from unittest.mock import MagicMock, patch

        state = sync.SyncState()
        state.enable_sync_drive = True
        config = {
            "drive": {
                "destination": self.tmp,
                "require_mount_marker": True,
            },
        }
        with patch.object(
            sync.config_parser,
            "prepare_drive_destination",
            return_value=self.tmp,
        ):
            result = sync._perform_drive_sync(  # noqa: SLF001
                config=config,
                api=MagicMock(),
                sync_state=state,
                drive_sync_interval=300,
            )
        self.assertIsNone(result)


class TestPhotosCheckCoversLibraryDestinations(unittest.TestCase):
    """``_perform_photos_sync`` must check the marker in every
    ``library_destinations`` subdir, not only the root.

    Patches ``prepare_photos_destination`` to return our tempdir and stubs
    out the iCloud API; the test only exercises the marker check + return
    path. ``photos.library_destinations`` mappings are read directly from
    config so this PR is independent of the library_destinations PR.
    """

    def setUp(self):
        """Tempdir with personal + shared subdirs (no markers yet)."""
        self.tmp = tempfile.mkdtemp()
        self.personal = os.path.join(self.tmp, "personal")
        self.shared = os.path.join(self.tmp, "shared")
        os.makedirs(self.personal)
        os.makedirs(self.shared)

    def tearDown(self):
        """Remove the tempdir."""
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_state(self):
        """SyncState with photos sync enabled."""
        state = sync.SyncState()
        state.enable_sync_photos = True
        return state

    def _config(self):
        """Config with require_mount_marker + library_destinations."""
        return {
            "photos": {
                "destination": self.tmp,
                "require_mount_marker": True,
                "library_destinations": {
                    "PrimarySync": "personal",
                    "SharedLibrary": "shared",
                },
            },
        }

    def test_skips_when_root_has_marker_but_subdir_missing(self):
        """Root marker alone is not enough — each subdir must also have one."""
        from unittest.mock import patch

        open(os.path.join(self.tmp, ".mounted"), "w").close()
        open(os.path.join(self.personal, ".mounted"), "w").close()
        # shared/ deliberately missing marker.
        with patch.object(
            sync.config_parser,
            "prepare_photos_destination",
            return_value=self.tmp,
        ):
            result = sync._perform_photos_sync(  # noqa: SLF001
                config=self._config(),
                api=None,
                sync_state=self._make_state(),
                photos_sync_interval=300,
            )
        self.assertIsNone(result)

    def test_proceeds_when_all_subdirs_have_marker(self):
        """All markers present → marker gate opens (no missing-marker
        error logged). We don't care what happens after the gate; we
        only want to prove the gate opened."""
        from unittest.mock import MagicMock, patch

        for d in (self.tmp, self.personal, self.shared):
            open(os.path.join(d, ".mounted"), "w").close()
        fake_api = MagicMock()
        with (
            patch.object(
                sync.config_parser,
                "prepare_photos_destination",
                return_value=self.tmp,
            ),
            patch.object(
                sync.sync_photos,
                "sync_photos",
                return_value=set(),
            ),
            self.assertLogs(sync.LOGGER, level=logging.INFO) as cm,
        ):
            sync._perform_photos_sync(  # noqa: SLF001
                config=self._config(),
                api=fake_api,
                sync_state=self._make_state(),
                photos_sync_interval=300,
            )
        joined = "\n".join(cm.output)
        self.assertNotIn("Photos mount marker missing", joined)

    def test_non_string_or_empty_subdir_entries_are_skipped(self):
        """Defensive: if `library_destinations` contains non-string or
        empty values (mis-configured YAML, future schema drift), those
        entries don't crash — they're silently skipped from the marker
        check. Root + the one valid subdir still get checked normally."""
        from unittest.mock import MagicMock, patch

        # Only root + valid `personal` subdir get markers; the bad
        # entries should be skipped, NOT cause a marker-missing error.
        for d in (self.tmp, self.personal):
            open(os.path.join(d, ".mounted"), "w").close()

        config = {
            "photos": {
                "destination": self.tmp,
                "require_mount_marker": True,
                "library_destinations": {
                    "PrimarySync": "personal",  # valid
                    "Bogus": "",  # empty string — skip
                    "Numeric": 42,  # non-string — skip
                },
            },
        }
        fake_api = MagicMock()
        with (
            patch.object(
                sync.config_parser,
                "prepare_photos_destination",
                return_value=self.tmp,
            ),
            patch.object(sync.sync_photos, "sync_photos", return_value=set()),
            self.assertLogs(sync.LOGGER, level=logging.INFO) as cm,
        ):
            sync._perform_photos_sync(  # noqa: SLF001
                config=config,
                api=fake_api,
                sync_state=self._make_state(),
                photos_sync_interval=300,
            )
        joined = "\n".join(cm.output)
        # Marker check passed: no "marker missing" for any path.
        self.assertNotIn("Photos mount marker missing", joined)


if __name__ == "__main__":
    unittest.main()
