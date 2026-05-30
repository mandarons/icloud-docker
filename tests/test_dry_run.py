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
        api = self._make_api(photos_libraries={"PrimarySync": object(), "SharedLibrary": object()})
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
        with patch("src.config_parser.get_username", return_value=data.AUTHENTICATED_USER):
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
        with patch("src.config_parser.get_username", return_value=data.AUTHENTICATED_USER):
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
        with patch("src.config_parser.get_username", return_value=data.AUTHENTICATED_USER):
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
        with patch("src.config_parser.get_username", return_value=data.AUTHENTICATED_USER):
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
