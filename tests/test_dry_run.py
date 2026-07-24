"""Tests for the ``--dry-run`` mode (sync.sync(dry_run=True) and the
``_perform_dry_run`` helper)."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import logging
import os
import shutil
import unittest
from unittest.mock import MagicMock, patch

import tests
from src import read_config, sync
from tests import data


class TestDryRunPerform(unittest.TestCase):
    """Direct tests of ``sync._perform_dry_run`` without going through ``sync.sync``."""

    def setUp(self):
        """Load the test config + a temp root each test."""
        config = read_config(config_path=tests.CONFIG_PATH)
        assert isinstance(config, dict)
        self.config = config
        self.config["app"]["root"] = tests.TEMP_DIR
        os.makedirs(tests.TEMP_DIR, exist_ok=True)

    def tearDown(self):
        """Remove temp dirs."""
        if os.path.exists(tests.TEMP_DIR):
            shutil.rmtree(tests.TEMP_DIR)

    def _make_api(self, drive_items=None, photos_libraries=None):
        """Build a minimal API mock with .drive.dir() and .photos.libraries."""
        api = MagicMock()
        api.drive.dir.return_value = drive_items or []
        api.photos.libraries = photos_libraries or {}
        return api

    def test_drive_destination_and_root_count_logged(self):
        """When Drive is configured, log destination path + root item count."""
        api = self._make_api(drive_items=["dir1", "dir2", "file.txt"])
        with self.assertLogs(sync.LOGGER, level=logging.INFO) as cm:
            sync._perform_dry_run(config=self.config, api=api)  # noqa: SLF001
        joined = "\n".join(cm.output)
        self.assertIn("DRY RUN: Drive destination:", joined)
        self.assertIn("Drive root contains 3 item(s)", joined)

    def test_photos_libraries_logged(self):
        """When Photos is configured, log destination path + library names."""
        api = self._make_api(
            photos_libraries={"PrimarySync": object(), "SharedLibrary": object()},
        )
        with self.assertLogs(sync.LOGGER, level=logging.INFO) as cm:
            sync._perform_dry_run(config=self.config, api=api)  # noqa: SLF001
        joined = "\n".join(cm.output)
        self.assertIn("DRY RUN: Photos destination:", joined)
        self.assertIn("PrimarySync", joined)
        self.assertIn("SharedLibrary", joined)

    def test_drive_enumeration_failure_is_non_fatal(self):
        """Exception inside drive.dir() is caught and logged as a warning."""
        api = MagicMock()
        api.drive.dir.side_effect = RuntimeError("boom")
        api.photos.libraries = {}
        with self.assertLogs(sync.LOGGER, level=logging.WARNING) as cm:
            sync._perform_dry_run(config=self.config, api=api)  # noqa: SLF001
        joined = "\n".join(cm.output)
        self.assertIn("Drive enumeration failed", joined)
        self.assertIn("boom", joined)

    def test_photos_enumeration_failure_is_non_fatal(self):
        """Exception while accessing photos.libraries is caught and logged."""

        class BoomPhotos:
            @property
            def libraries(self):
                raise RuntimeError("photos boom")  # noqa: EM101

        api = self._make_api(drive_items=[])
        api.photos = BoomPhotos()
        with self.assertLogs(sync.LOGGER, level=logging.WARNING) as cm:
            sync._perform_dry_run(config=self.config, api=api)  # noqa: SLF001
        joined = "\n".join(cm.output)
        self.assertIn("Photos enumeration failed", joined)

    def test_completion_line_logged(self):
        """Final 'DRY RUN complete' line is always emitted."""
        api = self._make_api()
        with self.assertLogs(sync.LOGGER, level=logging.INFO) as cm:
            sync._perform_dry_run(config=self.config, api=api)  # noqa: SLF001
        joined = "\n".join(cm.output)
        self.assertIn("DRY RUN complete", joined)
        self.assertIn("--dry-run", joined)

    def test_skipped_services_announced(self):
        """When a service is not configured, log that it would be skipped."""
        config = {"app": dict(self.config["app"])}  # no drive, no photos
        api = self._make_api()
        with self.assertLogs(sync.LOGGER, level=logging.INFO) as cm:
            sync._perform_dry_run(config=config, api=api)  # noqa: SLF001
        joined = "\n".join(cm.output)
        self.assertIn("no `drive:` section in config", joined)
        self.assertIn("no `photos:` section in config", joined)


class TestDryRunCheckFilesIntegration(unittest.TestCase):
    """``--check-files N`` triggers the migration_check walk for both
    photos and drive. Tests the integration layer in ``_perform_dry_run``
    that wires args.check_files through to migration_check.check_migration
    and migration_check.check_drive_migration, then formats the per-status
    sample lines for the operator's log."""

    def setUp(self):
        config = read_config(config_path=tests.CONFIG_PATH)
        assert isinstance(config, dict)
        self.config = config
        self.config["app"]["root"] = tests.TEMP_DIR
        os.makedirs(tests.TEMP_DIR, exist_ok=True)

    def tearDown(self):
        if os.path.exists(tests.TEMP_DIR):
            shutil.rmtree(tests.TEMP_DIR)

    def _photos_result(self):
        """Fake check_migration result with one library + 3 sample
        statuses so every sample-line formatter branch is exercised."""
        return {
            "PrimarySync": {
                "library_dest": "/photos/personal",
                "checked": 5,
                "stats": {
                    "would_skip": 2,
                    "size_mismatch": 1,
                    "not_found": 1,
                    "error": 1,
                },
                "samples": {
                    "would_skip": [("/photos/personal/IMG_1.HEIC", 1000)],
                    "size_mismatch": [
                        ("/photos/personal/IMG_2.HEIC", 1000, 800),
                    ],
                    "not_found": [("/photos/personal/IMG_3.HEIC", 500)],
                },
            },
        }

    def _drive_result(self):
        return {
            "drive_destination": "/icloud/drive",
            "checked": 4,
            "stats": {
                "would_skip": 1,
                "size_mismatch": 1,
                "not_found": 1,
                "error": 1,
            },
            "samples": {
                "would_skip": [("/icloud/drive/a.txt", 100)],
                "size_mismatch": [("/icloud/drive/b.txt", 200, 150)],
                "not_found": [("/icloud/drive/c.txt", 300)],
            },
        }

    def test_check_files_invokes_both_walkers_and_logs_per_status(self):
        """Happy path: check_files=10 → call check_migration AND
        check_drive_migration, then log per-library + per-drive stats
        AND each sample line (would_skip/size_mismatch/not_found)."""
        from unittest.mock import MagicMock, patch

        api = MagicMock()
        with patch.object(
            sync,
            "config_parser",
        ) as fake_cp, patch(
            "src.migration_check.check_migration",
            return_value=self._photos_result(),
        ) as fake_photos, patch(
            "src.migration_check.check_drive_migration",
            return_value=self._drive_result(),
        ) as fake_drive, self.assertLogs(
            sync.LOGGER, level=logging.INFO,
        ) as cm:
            fake_cp.prepare_drive_destination.return_value = "/icloud/drive"
            fake_cp.prepare_photos_destination.return_value = "/icloud/photos"
            sync._perform_dry_run(  # noqa: SLF001
                config=self.config,
                api=api,
                check_files=10,
            )
        fake_photos.assert_called_once_with(api=api, config=self.config, sample=10)
        fake_drive.assert_called_once_with(api=api, config=self.config, sample=10)
        joined = "\n".join(cm.output)
        self.assertIn("walking photos for file-existence check", joined)
        self.assertIn("PrimarySync", joined)
        self.assertIn("would_skip=2", joined)
        # Sample formatter lines:
        self.assertIn("sample would_skip:", joined)
        self.assertIn("sample size_mismatch:", joined)
        self.assertIn("sample not_found:", joined)
        # Drive section:
        self.assertIn("sampled=4", joined)

    def test_check_files_zero_means_walk_all(self):
        """check_files=0 is passed straight through and the log says
        'all' instead of a number."""
        from unittest.mock import MagicMock, patch

        api = MagicMock()
        with patch(
            "src.migration_check.check_migration",
            return_value={},
        ), patch(
            "src.migration_check.check_drive_migration",
            return_value=None,
        ), self.assertLogs(sync.LOGGER, level=logging.INFO) as cm:
            sync._perform_dry_run(  # noqa: SLF001
                config=self.config,
                api=api,
                check_files=0,
            )
        joined = "\n".join(cm.output)
        self.assertIn("--check-files=all", joined)

    def test_photos_check_files_walk_failure_logged_as_warning(self):
        """If migration_check.check_migration raises, the failure is a
        WARNING (not a fatal crash) — the rest of the dry-run continues."""
        from unittest.mock import MagicMock, patch

        api = MagicMock()
        with patch(
            "src.migration_check.check_migration",
            side_effect=RuntimeError("photos boom"),
        ), patch(
            "src.migration_check.check_drive_migration",
            return_value=None,
        ), self.assertLogs(
            sync.LOGGER, level=logging.WARNING,
        ) as cm:
            sync._perform_dry_run(  # noqa: SLF001
                config=self.config,
                api=api,
                check_files=10,
            )
        joined = "\n".join(cm.output)
        self.assertIn("photos check-files walk failed", joined)

    def test_drive_check_files_walk_failure_logged_as_warning(self):
        """If migration_check.check_drive_migration raises, the failure
        is a WARNING — doesn't crash _perform_dry_run."""
        from unittest.mock import MagicMock, patch

        api = MagicMock()
        with patch(
            "src.migration_check.check_migration",
            return_value={},
        ), patch(
            "src.migration_check.check_drive_migration",
            side_effect=RuntimeError("drive boom"),
        ), self.assertLogs(sync.LOGGER, level=logging.WARNING) as cm:
            sync._perform_dry_run(  # noqa: SLF001
                config=self.config,
                api=api,
                check_files=10,
            )
        joined = "\n".join(cm.output)
        self.assertIn("drive check-files walk failed", joined)

    def test_check_files_none_skips_migration_walks(self):
        """Default check_files=None → migration_check is NEVER called."""
        from unittest.mock import patch

        api = self._make_api()
        with patch(
            "src.migration_check.check_migration",
        ) as fake_photos, patch(
            "src.migration_check.check_drive_migration",
        ) as fake_drive:
            sync._perform_dry_run(config=self.config, api=api)  # noqa: SLF001
        fake_photos.assert_not_called()
        fake_drive.assert_not_called()

    def _make_api(self):
        from unittest.mock import MagicMock

        api = MagicMock()
        api.drive.dir.return_value = []
        api.photos.libraries = {}
        return api


class TestSyncDryRunIntegration(unittest.TestCase):
    """Integration: ``sync.sync(dry_run=True)`` short-circuits the loop."""

    def setUp(self):
        """Reset temp + load config."""
        config = read_config(config_path=tests.CONFIG_PATH)
        assert isinstance(config, dict)
        self.config = config
        self.config["app"]["root"] = tests.TEMP_DIR
        os.makedirs(tests.TEMP_DIR, exist_ok=True)

    def tearDown(self):
        """Cleanup."""
        if os.path.exists(tests.TEMP_DIR):
            shutil.rmtree(tests.TEMP_DIR)

    @patch("src.sync._perform_dry_run")
    @patch("src.sync._perform_photos_sync")
    @patch("src.sync._perform_drive_sync")
    @patch("src.sync._authenticate_and_get_api")
    @patch("src.sync.alive")
    @patch("src.sync._load_configuration")
    def test_dry_run_invokes_perform_dry_run_and_skips_syncs(
        self,
        mock_load_config,
        mock_alive,
        mock_auth,
        mock_drive_sync,
        mock_photos_sync,
        mock_perform_dry_run,
    ):
        """dry_run=True → _perform_dry_run is called; the real syncs are not."""
        mock_load_config.return_value = self.config
        # Make get_username return something truthy.
        with patch(
            "src.config_parser.get_username", return_value=data.AUTHENTICATED_USER,
        ):
            api = MagicMock()
            api.requires_2sa = False
            mock_auth.return_value = api

            sync.sync(dry_run=True)

        mock_perform_dry_run.assert_called_once()
        mock_drive_sync.assert_not_called()
        mock_photos_sync.assert_not_called()

    @patch("src.sync.notify.send_sync_summary")
    @patch("src.sync._perform_dry_run")
    @patch("src.sync._authenticate_and_get_api")
    @patch("src.sync.alive")
    @patch("src.sync._load_configuration")
    def test_dry_run_does_not_send_notifications(
        self,
        mock_load_config,
        mock_alive,
        mock_auth,
        mock_perform_dry_run,
        mock_notify_send,
    ):
        """No sync summary notification under dry-run."""
        mock_load_config.return_value = self.config
        with patch(
            "src.config_parser.get_username", return_value=data.AUTHENTICATED_USER,
        ):
            api = MagicMock()
            api.requires_2sa = False
            mock_auth.return_value = api
            sync.sync(dry_run=True)
        mock_notify_send.assert_not_called()

    @patch("src.sync._perform_dry_run")
    @patch("src.sync._authenticate_and_get_api")
    @patch("src.sync.sleep")
    @patch("src.sync.alive")
    @patch("src.sync._load_configuration")
    def test_dry_run_does_not_loop(
        self,
        mock_load_config,
        mock_alive,
        mock_sleep,
        mock_auth,
        mock_perform_dry_run,
    ):
        """sync(dry_run=True) returns after a single authenticate — never sleeps."""
        mock_load_config.return_value = self.config
        with patch(
            "src.config_parser.get_username", return_value=data.AUTHENTICATED_USER,
        ):
            api = MagicMock()
            api.requires_2sa = False
            mock_auth.return_value = api
            sync.sync(dry_run=True)
        # If we got here without timing out, the loop exited. Sanity-check:
        mock_sleep.assert_not_called()
        mock_perform_dry_run.assert_called_once()

    @patch("src.sync._perform_dry_run")
    @patch("src.sync._authenticate_and_get_api")
    @patch("src.sync.alive")
    @patch("src.sync._load_configuration")
    def test_dry_run_with_2fa_required_skips_perform_dry_run(
        self,
        mock_load_config,
        mock_alive,
        mock_auth,
        mock_perform_dry_run,
    ):
        """If 2FA is pending, dry-run logs a message and exits without enumerating."""
        mock_load_config.return_value = self.config
        with patch(
            "src.config_parser.get_username", return_value=data.AUTHENTICATED_USER,
        ):
            api = MagicMock()
            api.requires_2sa = True
            mock_auth.return_value = api
            with self.assertLogs(sync.LOGGER, level=logging.INFO) as cm:
                sync.sync(dry_run=True)
        joined = "\n".join(cm.output)
        self.assertIn("DRY RUN: 2FA required", joined)
        mock_perform_dry_run.assert_not_called()


class TestSyncSignatureBackwardCompat(unittest.TestCase):
    """``sync.sync()`` (no args) must still work — dry_run default is False."""

    def test_dry_run_default_is_false(self):
        """Default parameter binding."""
        import inspect

        sig = inspect.signature(sync.sync)
        self.assertIn("dry_run", sig.parameters)
        self.assertEqual(sig.parameters["dry_run"].default, False)


if __name__ == "__main__":
    unittest.main()
