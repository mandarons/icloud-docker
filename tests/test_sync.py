"""Tests for sync.py file."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import copy
import datetime
import os
import shutil
import unittest
from copy import deepcopy
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from icloudpy import exceptions

import tests
from src import ENV_ICLOUD_PASSWORD_KEY, config_parser, read_config, sync
from src.sync_stats import DriveStats, PhotoStats
from tests import data


class _IndexingPhotos:
    """A photo service Apple has not finished indexing.

    Faithful to icloudpy 0.10.0: a zone is opened by constructing a
    ``PhotoLibrary``, whose constructor raises ServiceNotActivated when
    that zone's index is unfinished, and ``PhotosService.libraries``
    builds one for every zone of the account in a single loop without
    caching anything on failure. Every access therefore raises, which is
    why one indexing zone makes the whole service unreadable.
    """

    @property
    def libraries(self):
        """Raise what icloudpy raises, message and all."""
        msg = "iCloud Photo Library not finished indexing.  Please try again in a few minutes"
        raise exceptions.ICloudPyServiceNotActivatedException(msg, None)


class TestSync(unittest.TestCase):
    """Tests class for sync.py file."""

    def remove_temp(self):
        """Remove all temp paths."""
        if os.path.exists(tests.TEMP_DIR):
            shutil.rmtree(tests.TEMP_DIR)
        if os.path.exists("session_data"):
            shutil.rmtree("session_data")
        if os.path.exists("icloud"):
            shutil.rmtree("icloud")

    def setUp(self) -> None:
        """Initialize tests."""
        config = read_config(config_path=tests.CONFIG_PATH)
        assert isinstance(config, dict)
        self.config = config
        self.root_dir = tests.TEMP_DIR
        self.config["app"]["root"] = self.root_dir
        os.makedirs(tests.TEMP_DIR, exist_ok=True)
        self.service = data.ICloudPyServiceMock(data.AUTHENTICATED_USER, data.VALID_PASSWORD)

    def tearDown(self) -> None:
        """Remove temp directories."""
        self.remove_temp()

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        """Test for valid sync."""
        config = self.config.copy()
        mock_read_config.return_value = config
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]
        self.assertIsNone(sync.sync())
        # Resolves to the conftest's tempdir on non-container hosts;
        # ``/config/session_data`` in a real container deployment.
        from src import DEFAULT_COOKIE_DIRECTORY

        self.assertTrue(os.path.isdir(DEFAULT_COOKIE_DIRECTORY))

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_photos_only(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        """Test for syncing only photos."""
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]
        # Sync only photos
        config = self.config.copy()
        del config["drive"]
        self.remove_temp()
        mock_read_config.return_value = config
        self.assertIsNone(sync.sync())
        dir_contents = os.listdir(self.root_dir)
        self.assertTrue(os.path.isdir(os.path.join(self.root_dir, config["photos"]["destination"])))
        # Root contains the destination dir and the usage cache file (`.data`)
        self.assertGreaterEqual(len(dir_contents), 1)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_drive_only(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        """Test for syncing only drive."""
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        # Sync only drive
        config = self.config.copy()
        del config["photos"]
        self.remove_temp()
        mock_read_config.return_value = config
        self.assertIsNone(sync.sync())
        self.assertTrue(os.path.isdir(os.path.join(self.root_dir, config["drive"]["destination"])))
        dir_contents = os.listdir(self.root_dir)
        # Root contains the destination dir and the usage cache file (`.data`)
        self.assertGreaterEqual(len(dir_contents), 1)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_empty(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        """Test for nothing to sync."""
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        # Nothing to sync
        config = self.config.copy()
        del config["photos"]
        del config["drive"]
        self.remove_temp()
        mock_read_config.return_value = config
        self.assertIsNone(sync.sync())
        self.assertTrue(os.path.exists(self.root_dir))

    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_2fa_required(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        """Test for 2fa required."""
        config = self.config.copy()
        mock_read_config.return_value = config
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        with self.assertLogs() as captured:
            mock_get_username.return_value = data.REQUIRES_2FA_USER
            mock_sleep.side_effect = [
                None,
                Exception(),
            ]
            with self.assertRaises(Exception):
                sync.sync()
        self.assertTrue(len(captured.records) > 1)
        self.assertTrue(len([e for e in captured[1] if "2FA is required" in e]) > 0)

    def _run_2fa_handler(self, sync_state, api):
        """Invoke the private 2FA handler with this test's config/user."""
        return sync._handle_2fa_required(self.config, data.REQUIRES_2FA_USER, sync_state, api)  # noqa: SLF001

    @patch("src.sync.sleep")
    @patch("src.sync.notify.send", return_value=None)
    def test_handle_2fa_requests_push_once_per_episode(self, _mock_notify, _mock_sleep):
        """A 2FA push is requested exactly once per re-auth episode."""
        sync_state = sync.SyncState()
        api = Mock()

        with self.assertLogs() as captured:
            self.assertTrue(self._run_2fa_handler(sync_state, api))
        api.trigger_2fa_push_notification.assert_called_once()
        self.assertTrue(sync_state.two_fa_triggered)
        self.assertTrue(any("Requested a 2FA push notification" in e for e in captured[1]))

        # Second retry within the same episode must NOT push again.
        self.assertTrue(self._run_2fa_handler(sync_state, api))
        api.trigger_2fa_push_notification.assert_called_once()

    @patch("src.sync.sleep")
    @patch("src.sync.notify.send", return_value=None)
    def test_handle_2fa_push_failure_is_non_fatal(self, _mock_notify, _mock_sleep):
        """A failing trigger is swallowed; the retry loop still continues."""
        sync_state = sync.SyncState()
        api = Mock()
        api.trigger_2fa_push_notification.side_effect = RuntimeError("no trusted device")

        with self.assertLogs() as captured:
            self.assertTrue(self._run_2fa_handler(sync_state, api))
        # Not latched: one transient failure must not forfeit the push for the
        # whole re-auth episode -- the next cycle asks again.
        self.assertFalse(sync_state.two_fa_triggered)
        self.assertTrue(any("Failed to request 2FA push notification" in e for e in captured[1]))
        api.trigger_2fa_push_notification.side_effect = None
        api.trigger_2fa_push_notification.return_value = True
        self.assertTrue(self._run_2fa_handler(sync_state, api))
        self.assertEqual(api.trigger_2fa_push_notification.call_count, 2)
        self.assertTrue(sync_state.two_fa_triggered)

    @patch("src.sync._auth_retry_sleep")
    @patch("src.sync.notify.send", return_value=None)
    def test_a_rejected_push_request_is_retried_next_cycle(self, _mock_notify, _mock_sleep):
        """trigger_2fa_push_notification reports most failures by returning
        False, not by raising -- that must not latch either."""
        sync_state = sync.SyncState()
        api = Mock()
        api.trigger_2fa_push_notification.return_value = False
        with self.assertLogs() as captured:
            self.assertTrue(self._run_2fa_handler(sync_state, api))
        self.assertFalse(sync_state.two_fa_triggered)
        self.assertTrue(any("did not accept the 2FA push request" in e for e in captured[1]))

    @patch("src.sync.notify.send", return_value=None)
    def test_exit_mode_still_requests_the_push(self, _mock_notify):
        """retry_login_interval < 0 means an operator is about to step in by
        hand -- exactly when a code on their devices is needed."""
        config = copy.deepcopy(self.config)
        config["app"]["credentials"]["retry_login_interval"] = -1
        sync_state = sync.SyncState()
        api = Mock()
        api.trigger_2fa_push_notification.return_value = True
        self.assertFalse(
            sync._handle_2fa_required(config, data.REQUIRES_2FA_USER, sync_state, api),  # noqa: SLF001
        )
        api.trigger_2fa_push_notification.assert_called_once()

    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    # No password means the loop now builds a session-only client, so this
    # has to be stubbed or the test would depend on whatever session file
    # another test left in the shared cookie directory.
    @patch(
        "src.sync.SessionOnlyICloudPyService",
        side_effect=exceptions.ICloudPyNoStoredPasswordAvailableException(
            "No Apple ID password is stored and there is no saved session to resume.",
        ),
    )
    def test_sync_password_missing_in_keyring(
        self,
        mock_session_only,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        """Test for missing password in keyring."""
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]
        config = self.config.copy()
        mock_read_config.return_value = config
        with self.assertLogs() as captured:
            mock_get_password.return_value = None
            mock_sleep.side_effect = [
                None,
                Exception(),
            ]
            with self.assertRaises(Exception):
                sync.sync()
            self.assertTrue(
                len(
                    [
                        e
                        for e in captured[1]
                        if "No Apple ID password is stored" in e
                    ],
                )
                > 0,
            )

    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value="keyring_password")
    @patch(target="src.config_parser.get_username", return_value=data.REQUIRES_2FA_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_password_as_environment_variable(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        """Test for password as env variable."""
        config = self.config.copy()
        mock_read_config.return_value = config
        with self.assertLogs() as captured:
            mock_sleep.side_effect = [
                None,
                Exception(),
            ]
            with patch.dict(os.environ, {ENV_ICLOUD_PASSWORD_KEY: data.VALID_PASSWORD}):
                with self.assertRaises(Exception):
                    sync.sync()
                self.assertTrue(len([e for e in captured[1] if "Error: 2FA is required. Please log in." in e]) > 0)

    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_exception_thrown(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        """Test for exception."""
        config = self.config.copy()
        config["drive"]["sync_interval"] = 1
        config["drive"]["sync_interval"] = 1
        mock_read_config.return_value = config
        mock_sleep.side_effect = Exception()
        config = self.config.copy()
        mock_read_config.return_value = config
        with self.assertRaises(Exception):
            sync.sync()

    @patch("src.sync.sync_drive")
    @patch("src.sync.sync_photos")
    @patch(target="sys.stdout", new_callable=StringIO)
    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_different_schedule(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
        mock_stdout,
        mock_sync_photos,
        mock_sync_drive,
    ):
        """Test different schedule for drive and photos."""
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]
        config = self.config.copy()
        config["drive"]["sync_interval"] = 1
        config["photos"]["sync_interval"] = 2
        mock_read_config.return_value = config
        mock_sync_drive.sync_drive.return_value = None
        mock_sync_photos.sync_photos.return_value = None

        mock_sleep.side_effect = [
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            Exception(),
        ]
        with self.assertRaises(Exception):
            sync.sync()
        # Seven 1-second sleeps after the startup pass: Drive (every 1s)
        # syncs at t=0..7, Photos (every 2s) at t=0, 2, 4 and 6. No sleep is
        # ever longer than the shorter interval, and none is zero.
        self.assertEqual([c.args for c in mock_sleep.call_args_list], [(1,)] * 8)
        self.assertEqual(mock_sync_drive.sync_drive.call_count, 8)
        self.assertEqual(mock_sync_photos.sync_photos.call_count, 4)

    @patch("src.sync.sync_drive")
    def test_perform_drive_sync_collects_existing_files(self, mock_sync_drive):
        """Ensure files before sync are captured to compute new file stats."""

        sync_state = sync.SyncState()
        api = SimpleNamespace(drive=object())
        destination_path = config_parser.prepare_drive_destination(config=self.config)

        existing_file_path = os.path.join(destination_path, "existing.txt")
        with open(existing_file_path, "w", encoding="utf-8") as handle:
            handle.write("old content")

        new_file_path = os.path.join(destination_path, "new.txt")

        def fake_sync_drive(config, drive):
            with open(new_file_path, "w", encoding="utf-8") as handle:
                handle.write("fresh data")
            return {existing_file_path, new_file_path}

        mock_sync_drive.sync_drive.side_effect = fake_sync_drive

        stats = sync._perform_drive_sync(  # noqa: SLF001
            config=self.config,
            api=api,
            sync_state=sync_state,
            drive_sync_interval=42,
        )

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.files_downloaded, 1)
        self.assertEqual(stats.files_skipped, 1)
        self.assertGreater(stats.bytes_downloaded, 0)
        self.assertEqual(sync_state.drive_time_remaining, 42)

    @patch("src.sync.os.walk", side_effect=RuntimeError("walk failed"))
    @patch("src.sync.sync_drive")
    def test_perform_drive_sync_handles_walk_failure(self, mock_sync_drive, _mock_walk):
        """Handle errors from os.walk gracefully when counting existing files."""

        sync_state = sync.SyncState()
        api = SimpleNamespace(drive=object())
        destination_path = config_parser.prepare_drive_destination(config=self.config)
        new_file_path = os.path.join(destination_path, "new_from_sync.txt")

        def fake_sync_drive(config, drive):
            with open(new_file_path, "w", encoding="utf-8") as handle:
                handle.write("fresh data")
            return {new_file_path}

        mock_sync_drive.sync_drive.side_effect = fake_sync_drive

        stats = sync._perform_drive_sync(  # noqa: SLF001
            config=self.config,
            api=api,
            sync_state=sync_state,
            drive_sync_interval=60,
        )

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.files_downloaded, 1)
        self.assertEqual(stats.files_skipped, 0)
        self.assertGreater(stats.bytes_downloaded, 0)
        self.assertEqual(sync_state.drive_time_remaining, 60)

    @patch("src.sync.os.path.getsize", side_effect=RuntimeError("size failure"))
    @patch("src.sync.sync_drive")
    def test_perform_drive_sync_handles_getsize_failure(self, mock_sync_drive, _mock_getsize):
        """Gracefully handle size calculation failures when counting new files."""

        sync_state = sync.SyncState()
        api = SimpleNamespace(drive=object())
        destination_path = config_parser.prepare_drive_destination(config=self.config)

        existing_file_path = os.path.join(destination_path, "existing.txt")
        with open(existing_file_path, "w", encoding="utf-8") as handle:
            handle.write("old content")

        new_file_path = os.path.join(destination_path, "new.txt")

        def fake_sync_drive(config, drive):
            with open(new_file_path, "w", encoding="utf-8") as handle:
                handle.write("fresh data")
            return {existing_file_path, new_file_path}

        mock_sync_drive.sync_drive.side_effect = fake_sync_drive

        stats = sync._perform_drive_sync(  # noqa: SLF001
            config=self.config,
            api=api,
            sync_state=sync_state,
            drive_sync_interval=99,
        )

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.files_downloaded, 1)
        self.assertEqual(stats.bytes_downloaded, 0)
        self.assertEqual(sync_state.drive_time_remaining, 99)

    @patch("src.sync.os.listdir", side_effect=RuntimeError("list failure"))
    @patch("src.sync.os.walk")
    @patch("src.sync.sync_photos.sync_photos")
    def test_perform_photos_sync_handles_walk_and_list_errors(
        self,
        mock_sync_photos,
        mock_walk,
        _mock_listdir,
    ):
        """Photos sync should swallow filesystem errors when collecting stats."""

        def raise_every_call(_path):
            message = "walk failure"
            raise RuntimeError(message)

        mock_walk.side_effect = raise_every_call

        sync_state = sync.SyncState()
        api = SimpleNamespace(photos=object())
        config = deepcopy(self.config)

        stats = sync._perform_photos_sync(  # noqa: SLF001
            config=config,
            api=api,
            sync_state=sync_state,
            photos_sync_interval=15,
        )

        mock_sync_photos.assert_called_once()
        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertEqual(stats.photos_downloaded, 0)
        self.assertEqual(stats.photos_skipped, 0)
        self.assertEqual(stats.bytes_downloaded, 0)
        self.assertEqual(sync_state.photos_time_remaining, 15)

    @patch("src.sync.sync_photos.sync_photos")
    def test_perform_photos_sync_records_hardlink_stats(self, mock_sync_photos):
        """Ensure hardlink statistics and bytes saved calculation execute."""

        class TrackingSet(set):
            def __sub__(self, other):  # noqa: D401, ANN001
                return TrackingSet()

        config = deepcopy(self.config)
        config["photos"]["use_hardlinks"] = True
        sync_state = sync.SyncState()
        api = SimpleNamespace(photos=object())

        destination_path = config_parser.prepare_photos_destination(config=config)
        existing_file_path = os.path.join(destination_path, "existing.jpg")
        with open(existing_file_path, "w", encoding="utf-8") as handle:
            handle.write("old content")

        def fake_sync_photos(config, photos):  # noqa: ARG001
            album_dir = os.path.join(destination_path, "album_one")
            os.makedirs(album_dir, exist_ok=True)
            new_file_path = os.path.join(album_dir, "new.jpg")
            with open(new_file_path, "w", encoding="utf-8") as handle:
                handle.write("new content")

        mock_sync_photos.side_effect = fake_sync_photos
        api.photos = object()

        with (
            patch("src.sync.set", TrackingSet),
            patch(
                "src.sync.config_parser.get_photos_use_hardlinks",
                return_value=True,
            ),
        ):
            stats = sync._perform_photos_sync(  # noqa: SLF001
                config=config,
                api=api,
                sync_state=sync_state,
                photos_sync_interval=25,
            )

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertGreater(stats.photos_hardlinked, 0)
        self.assertGreater(stats.bytes_saved_by_hardlinks, 0)
        self.assertEqual(sync_state.photos_time_remaining, 25)
        self.assertTrue(mock_sync_photos.called)

    @patch("src.sync.os.path.getsize")
    @patch("src.sync.sync_photos.sync_photos")
    def test_perform_photos_sync_handles_hardlink_bytes_failure(self, mock_sync_photos, mock_getsize):
        """Handle errors when estimating bytes saved by hardlinks."""

        class TrackingSet(set):
            def __sub__(self, other):  # noqa: D401, ANN001
                return TrackingSet()

        config = deepcopy(self.config)
        config["photos"]["use_hardlinks"] = True
        sync_state = sync.SyncState()
        api = SimpleNamespace(photos=object())

        destination_path = config_parser.prepare_photos_destination(config=config)
        existing_file_path = os.path.join(destination_path, "existing.jpg")
        with open(existing_file_path, "w", encoding="utf-8") as handle:
            handle.write("old content")

        def fake_sync_photos(config, photos):  # noqa: ARG001
            album_dir = os.path.join(destination_path, "album_two")
            os.makedirs(album_dir, exist_ok=True)
            new_file_path = os.path.join(album_dir, "new.jpg")
            with open(new_file_path, "w", encoding="utf-8") as handle:
                handle.write("new content")

        mock_sync_photos.side_effect = fake_sync_photos
        api.photos = object()

        def raise_on_getsize(_path):
            message = "size failure"
            raise RuntimeError(message)

        mock_getsize.side_effect = raise_on_getsize

        with (
            patch("src.sync.set", TrackingSet),
            patch(
                "src.sync.config_parser.get_photos_use_hardlinks",
                return_value=True,
            ),
        ):
            stats = sync._perform_photos_sync(  # noqa: SLF001
                config=config,
                api=api,
                sync_state=sync_state,
                photos_sync_interval=35,
            )

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertGreater(stats.photos_hardlinked, 0)
        self.assertEqual(stats.bytes_saved_by_hardlinks, 0)
        self.assertEqual(sync_state.photos_time_remaining, 35)
        mock_getsize.assert_called()

    @patch("src.sync.sync_photos.sync_photos")
    def test_perform_photos_sync_tracks_failed_downloads(self, mock_sync_photos):
        """Failed photo downloads should be recorded in stats.errors."""
        config = deepcopy(self.config)
        sync_state = sync.SyncState()
        api = SimpleNamespace(photos=object())

        # Simulate sync returning (3 successful, 5 failed) downloads
        mock_sync_photos.return_value = (3, 5)

        stats = sync._perform_photos_sync(  # noqa: SLF001
            config=config,
            api=api,
            sync_state=sync_state,
            photos_sync_interval=10,
        )

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertTrue(stats.has_errors())
        self.assertEqual(len(stats.errors), 1)
        self.assertIn("5 photo download(s) failed", stats.errors[0])

    @patch("src.sync.sync_photos.sync_photos")
    def test_perform_photos_sync_no_errors_when_all_succeed(self, mock_sync_photos):
        """No errors should be recorded when all downloads succeed."""
        config = deepcopy(self.config)
        sync_state = sync.SyncState()
        api = SimpleNamespace(photos=object())

        # Simulate sync returning (10 successful, 0 failed)
        mock_sync_photos.return_value = (10, 0)

        stats = sync._perform_photos_sync(  # noqa: SLF001
            config=config,
            api=api,
            sync_state=sync_state,
            photos_sync_interval=10,
        )

        self.assertIsNotNone(stats)
        assert stats is not None
        self.assertFalse(stats.has_errors())
        self.assertEqual(len(stats.errors), 0)

    def test_photos_waits_for_apple_to_finish_indexing(self):
        """A wait, not a sync failure: Photos is skipped without an error,
        retried sooner than a long interval, and the dashboard is told.

        Driven through the real ``sync_photos`` so the exception travels
        the path icloudpy raises it on -- out of a zone lookup, through
        the per-library handler that must not swallow it.
        """
        sync_state = sync.SyncState()
        with (
            patch("src.web_signals.record_photos_indexing") as recorded,
            self.assertLogs(level="WARNING") as logs,
        ):
            stats = sync._perform_photos_sync(  # noqa: SLF001
                config=deepcopy(self.config),
                api=SimpleNamespace(photos=_IndexingPhotos()),
                sync_state=sync_state,
                photos_sync_interval=43200,
            )

        self.assertIsNone(stats)
        self.assertEqual(sync_state.photos_time_remaining, 1800)
        recorded.assert_called_once_with(waiting=True)
        self.assertTrue(any("has not finished indexing" in line for line in logs.output))
        self.assertTrue(any("again in 30 minutes" in line for line in logs.output))
        self.assertFalse(any(line.startswith("ERROR") for line in logs.output))

        # With Drive on its usual 12 hours, the next wake is for Photos.
        sync_state.drive_time_remaining = 43200
        config = {"drive": {}, "photos": {}}
        self.assertEqual(sync._calculate_next_sync_schedule(config, sync_state), 1800)  # noqa: SLF001
        self.assertTrue(sync_state.enable_sync_photos)
        self.assertFalse(sync_state.enable_sync_drive)

    def test_the_indexing_retry_only_ever_shortens_the_wait(self):
        """Never slower than the configured interval -- and still readable
        when that interval is shorter than a minute."""
        sync_state = sync.SyncState()
        with (
            patch("src.web_signals.record_photos_indexing", side_effect=OSError("read-only")),
            self.assertLogs(level="WARNING") as logs,
        ):
            sync._perform_photos_sync(  # noqa: SLF001
                config=deepcopy(self.config),
                api=SimpleNamespace(photos=_IndexingPhotos()),
                sync_state=sync_state,
                photos_sync_interval=45,
            )
        self.assertEqual(sync_state.photos_time_remaining, 45)
        self.assertTrue(any("again in 45 seconds" in line for line in logs.output))

    @patch("src.sync.sync_photos.sync_photos", return_value=(0, 0))
    def test_a_successful_photos_cycle_clears_the_indexing_note(self, _mock_sync_photos):
        """Otherwise the dashboard goes on saying Apple is indexing for as
        long as the container lives, having been right once."""
        with patch("src.web_signals.record_photos_indexing") as recorded:
            sync._perform_photos_sync(  # noqa: SLF001
                config=deepcopy(self.config),
                api=SimpleNamespace(photos=object()),
                sync_state=sync.SyncState(),
                photos_sync_interval=600,
            )
        recorded.assert_called_once_with(waiting=False)

    def test_the_wait_does_not_leave_a_library_reading_syncing_now(self):
        """The library being opened when indexing surfaced never started,
        so it must not be left mid-sync on the dashboard -- reading
        "Syncing now" beside a note saying Photos cannot be read."""
        from src import web_signals

        web_signals.record_library_started("PrimarySync")
        with self.assertLogs(level="WARNING"):
            sync._perform_photos_sync(  # noqa: SLF001
                config=deepcopy(self.config),
                api=SimpleNamespace(photos=_IndexingPhotos()),
                sync_state=sync.SyncState(),
                photos_sync_interval=43200,
            )
        states = web_signals.get_library_states()
        self.assertEqual(states["PrimarySync"]["state"], "interrupted")

    def test_a_one_shot_run_leaves_indexing_to_the_normal_error_path(self):
        """``sync_interval: -1`` runs one cycle and exits, so there is no
        later cycle to retry in -- and ``min`` would have scheduled the
        retry for -1 minutes and then not taken it."""
        with self.assertRaises(exceptions.ICloudPyServiceNotActivatedException):
            sync._perform_photos_sync(  # noqa: SLF001
                config=deepcopy(self.config),
                api=SimpleNamespace(photos=_IndexingPhotos()),
                sync_state=sync.SyncState(),
                photos_sync_interval=-1,
            )

    @patch("src.sync.sync_photos.sync_photos")
    def test_other_photos_service_errors_still_propagate(self, mock_sync_photos):
        """Only indexing is a wait. A dead zone is still a sync failure."""
        mock_sync_photos.side_effect = exceptions.ICloudPyServiceNotActivatedException("ZONE_NOT_FOUND", None)
        with self.assertRaises(exceptions.ICloudPyServiceNotActivatedException):
            sync._perform_photos_sync(  # noqa: SLF001
                config=deepcopy(self.config),
                api=SimpleNamespace(photos=object()),
                sync_state=sync.SyncState(),
                photos_sync_interval=600,
            )

    @patch("src.sync.notify.send_sync_summary", side_effect=RuntimeError("notify failure"))
    @patch("src.sync._perform_photos_sync")
    @patch("src.sync._perform_drive_sync", return_value=DriveStats(files_downloaded=1))
    @patch("src.sync._authenticate_and_get_api", return_value=SimpleNamespace(requires_2sa=False))
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_summary_notification_failure_logged(
        self,
        mock_usage_post,
        mock_read_config,
        _mock_auth,
        _mock_drive_sync,
        mock_photo_sync,
        mock_notify,
    ):
        """Sync loop should log and continue when summary notification fails."""

        from src.sync_stats import PhotoStats

        config = deepcopy(self.config)
        config["drive"]["sync_interval"] = -1
        config["photos"]["sync_interval"] = -1
        mock_read_config.return_value = config
        mock_photo_sync.return_value = PhotoStats(photos_downloaded=2)

        with self.assertLogs(sync.LOGGER, level="DEBUG") as captured_logs:
            sync.sync()

        mock_notify.assert_called()
        self.assertTrue(
            any("Failed to send sync summary notification" in message for message in captured_logs.output),
        )

    @patch("src.sync.read_config")
    def test_get_api_instance_default(
        self,
        mock_read_config,
    ):
        """Test for default api instance."""
        config = self.config.copy()
        config["app"]["region"] = "invalid"
        mock_read_config.return_value = config
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        actual = sync.get_api_instance(username=data.AUTHENTICATED_USER, password=data.VALID_PASSWORD)
        self.assertNotIn(".com.cn", actual.home_endpoint)
        self.assertNotIn(".com.cn", actual.setup_endpoint)

    @patch("src.sync.read_config")
    def test_get_api_instance_china_region(
        self,
        mock_read_config,
    ):
        """Test for china instance."""
        config = self.config.copy()
        config["app"]["region"] = "china"
        mock_read_config.return_value = config
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        actual = sync.get_api_instance(username=data.AUTHENTICATED_USER, password=data.VALID_PASSWORD)
        self.assertNotIn(".com.cn", actual.home_endpoint)
        self.assertNotIn(".com.cn", actual.setup_endpoint)

    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_negative_retry_login_interval(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        """Test for negative retry login interval."""
        config = self.config.copy()
        config["app"]["credentials"]["retry_login_interval"] = -1
        mock_read_config.return_value = config
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        with self.assertLogs() as captured:
            mock_get_username.return_value = data.REQUIRES_2FA_USER
            mock_sleep.side_effect = [
                None,
            ]
            sync.sync()
        self.assertTrue(len(captured.records) > 1)
        self.assertTrue(len([e for e in captured[1] if "2FA is required" in e]) > 0)
        self.assertTrue(len([e for e in captured[1] if "retry_login_interval is < 0, exiting ..." in e]) > 0)

    @patch("src.sync.sleep")
    @patch(
        target="keyring.get_password",
        side_effect=exceptions.ICloudPyNoStoredPasswordAvailableException,
    )
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    @patch(
        "src.sync.SessionOnlyICloudPyService",
        side_effect=exceptions.ICloudPyNoStoredPasswordAvailableException(
            "No Apple ID password is stored and there is no saved session to resume.",
        ),
    )
    def test_sync_negative_retry_login_interval_without_keyring_password(
        self,
        mock_session_only,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        """Test for negative retry login interval."""
        config = self.config.copy()
        config["app"]["credentials"]["retry_login_interval"] = -1
        mock_read_config.return_value = config
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        with self.assertLogs() as captured:
            mock_get_username.return_value = data.REQUIRES_2FA_USER
            mock_sleep.side_effect = [
                None,
            ]
            sync.sync()
        self.assertTrue(len(captured.records) > 1)
        self.assertTrue(len([e for e in captured[1] if "No Apple ID password is stored" in e]) > 0)
        self.assertTrue(len([e for e in captured[1] if "retry_login_interval is < 0, exiting ..." in e]) > 0)

    @patch("src.sync.sync_drive")
    @patch("src.sync.sync_photos")
    @patch("src.sync.sleep")
    @patch("src.usage.alive")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_oneshot_mode_both_negative(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_alive,
        mock_sleep,
        mock_sync_photos,
        mock_sync_drive,
    ):
        """Test oneshot mode when both drive and photos sync_interval are -1."""
        config = self.config.copy()
        config["drive"]["sync_interval"] = -1
        config["photos"]["sync_interval"] = -1
        mock_read_config.return_value = config
        mock_sync_drive.return_value = None
        mock_sync_photos.return_value = None
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        with self.assertLogs() as captured:
            sync.sync()

        # Verify the container exits with oneshot message
        self.assertTrue(len(captured.records) > 1)
        self.assertTrue(
            len([e for e in captured[1] if "All configured sync intervals are negative, exiting oneshot mode..." in e])
            > 0,
        )
        # Verify sleep is never called (container exits immediately after sync)
        mock_sleep.assert_not_called()

    @patch("src.sync.sync_drive")
    @patch("src.sync.sync_photos")
    @patch("src.sync.sleep")
    @patch("src.usage.alive")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_oneshot_mode_drive_only(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_alive,
        mock_sleep,
        mock_sync_photos,
        mock_sync_drive,
    ):
        """Test oneshot mode when only drive is configured with sync_interval -1."""
        config = self.config.copy()
        config["drive"]["sync_interval"] = -1
        del config["photos"]  # Only drive configured
        mock_read_config.return_value = config
        mock_sync_drive.sync_drive.return_value = None
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        with self.assertLogs() as captured:
            sync.sync()

        # Verify the container exits with oneshot message
        self.assertTrue(len(captured.records) > 1)
        self.assertTrue(
            len([e for e in captured[1] if "All configured sync intervals are negative, exiting oneshot mode..." in e])
            > 0,
        )
        # Verify sleep is never called
        mock_sleep.assert_not_called()

    @patch("src.sync.sync_drive")
    @patch("src.sync.sync_photos")
    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_mixed_intervals_should_not_exit(
        self,
        mock_usage_post,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
        mock_sync_photos,
        mock_sync_drive,
    ):
        """Test that container does NOT exit when only one sync_interval is -1."""
        config = self.config.copy()
        config["drive"]["sync_interval"] = -1  # Oneshot
        config["photos"]["sync_interval"] = 300  # Regular interval
        mock_read_config.return_value = config
        mock_sync_drive.return_value = None
        mock_sync_photos.return_value = None
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        # Mock sleep to raise exception after first call to break the loop
        mock_sleep.side_effect = [Exception("Break loop")]

        with self.assertRaises(Exception):
            with self.assertLogs() as captured:
                sync.sync()

        # Verify it does NOT exit with oneshot message
        oneshot_messages = [
            e for e in captured[1] if "All configured sync intervals are negative, exiting oneshot mode..." in e
        ]
        self.assertEqual(len(oneshot_messages), 0)
        # The loop continued, waiting for Photos -- not a negative sleep for
        # the one-shot Drive that has already run (time.sleep(-1) raises).
        mock_sleep.assert_called_once()
        self.assertGreater(mock_sleep.call_args.args[0], 0)

    @patch("src.sync.notify.send_sync_summary")
    @patch("src.sync._perform_photos_sync", return_value=None)
    @patch("src.sync._perform_drive_sync", return_value=DriveStats(files_downloaded=1))
    @patch("src.sync._authenticate_and_get_api", return_value=SimpleNamespace(requires_2sa=False))
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_notification_not_sent_when_both_services_not_synced(
        self,
        mock_usage_post,
        mock_read_config,
        _mock_auth,
        _mock_drive_sync,
        _mock_photo_sync,
        mock_notify,
    ):
        """Notification should not be sent when both services are configured but only one synced."""

        config = deepcopy(self.config)
        config["drive"]["sync_interval"] = -1
        config["photos"]["sync_interval"] = -1
        mock_read_config.return_value = config

        sync.sync()

        # Notification should NOT be called because photos didn't sync (returned None)
        mock_notify.assert_not_called()

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch("src.sync._send_usage_statistics")
    def test_usage_statistics_exception_handling(self, mock_send_stats, _mock_keyring):
        """Test that usage statistics exceptions are caught and logged."""
        config = deepcopy(self.config)
        config["username"] = data.AUTHENTICATED_USER
        config["drive"]["sync_interval"] = -1
        config["photos"]["sync_interval"] = -1

        # Mock _send_usage_statistics to raise an exception
        mock_send_stats.side_effect = RuntimeError("Network timeout")

        with (
            patch("src.sync.read_config") as mock_read_config,
            patch("src.sync._authenticate_and_get_api") as mock_auth,
            patch("src.sync._perform_drive_sync") as mock_drive,
            patch("src.sync._perform_photos_sync") as mock_photos,
            patch("src.sync._should_exit_oneshot_mode") as mock_exit,
        ):
            mock_read_config.return_value = config
            mock_auth.return_value = self.service
            mock_drive.return_value = DriveStats()
            mock_photos.return_value = None
            mock_exit.return_value = True

            # Should not raise exception despite _send_usage_statistics failure
            sync.sync()

            # Verify that usage statistics were attempted
            mock_send_stats.assert_called()

    def test_calculate_next_sync_schedule_equal_intervals_bug(self):
        """Test that equal sync intervals don't cause immediate re-sync (regression test)."""
        config = {
            "drive": {"sync_interval": 86400},  # 24 hours
            "photos": {"sync_interval": 86400},  # 24 hours
        }

        # Simulate state after both services just completed syncing
        sync_state = sync.SyncState()
        sync_state.drive_time_remaining = 86400
        sync_state.photos_time_remaining = 86400

        # Calculate next sync schedule
        sleep_for = sync._calculate_next_sync_schedule(config, sync_state)  # noqa: SLF001

        # This should NOT be 0 - that's the bug causing immediate re-sync
        # When both timers are equal and both services just ran, we should wait
        self.assertGreater(sleep_for, 0, "Sleep time should not be 0 when both services just completed")
        self.assertEqual(sleep_for, 86400, "Should wait for the full interval when both services have equal timers")

        # When timers are equal and > 10 seconds, both services should be enabled for next sync
        self.assertTrue(sync_state.enable_sync_drive, "Drive sync should be enabled")
        self.assertTrue(sync_state.enable_sync_photos, "Photos sync should be enabled")

    def test_calculate_next_sync_schedule_drive_first(self):
        """Test that drive syncs first when its timer is smaller."""
        config = {
            "drive": {"sync_interval": 3600},  # 1 hour
            "photos": {"sync_interval": 7200},  # 2 hours
        }

        sync_state = sync.SyncState()
        sync_state.drive_time_remaining = 1800  # 30 min remaining
        sync_state.photos_time_remaining = 3600  # 1 hour remaining

        sleep_for = sync._calculate_next_sync_schedule(config, sync_state)  # noqa: SLF001

        self.assertEqual(sleep_for, 1800, "Should sleep until drive sync time")
        self.assertTrue(sync_state.enable_sync_drive, "Drive sync should be enabled")
        self.assertFalse(sync_state.enable_sync_photos, "Photos sync should be disabled")
        self.assertEqual(sync_state.photos_time_remaining, 1800, "Photos timer should be reduced")

    def test_calculate_next_sync_schedule_photos_first(self):
        """Test that photos syncs first when its timer is smaller."""
        config = {
            "drive": {"sync_interval": 7200},  # 2 hours
            "photos": {"sync_interval": 3600},  # 1 hour
        }

        sync_state = sync.SyncState()
        sync_state.drive_time_remaining = 3600  # 1 hour remaining
        sync_state.photos_time_remaining = 1800  # 30 min remaining

        sleep_for = sync._calculate_next_sync_schedule(config, sync_state)  # noqa: SLF001

        self.assertEqual(sleep_for, 1800, "Should sleep until photos sync time")
        self.assertFalse(sync_state.enable_sync_drive, "Drive sync should be disabled")
        self.assertTrue(sync_state.enable_sync_photos, "Photos sync should be enabled")
        self.assertEqual(sync_state.drive_time_remaining, 1800, "Drive timer should be reduced")

    def test_calculate_next_sync_schedule_sleeps_until_the_sooner_service(self):
        """The sleep is the time to the next due service, not the gap between them.

        Drive every hour and Photos every 12 hours used to sleep 11 hours
        before the next Drive sync, because the difference of the two
        timers was taken as the sleep.
        """
        config = {
            "drive": {"sync_interval": 3600},
            "photos": {"sync_interval": 43200},
        }
        sync_state = sync.SyncState()
        sync_state.drive_time_remaining = 3600
        sync_state.photos_time_remaining = 43200

        sleep_for = sync._calculate_next_sync_schedule(config, sync_state)  # noqa: SLF001

        self.assertEqual(sleep_for, 3600)
        self.assertTrue(sync_state.enable_sync_drive)
        self.assertFalse(sync_state.enable_sync_photos)
        self.assertEqual(sync_state.photos_time_remaining, 39600)

        # And the other way round.
        sync_state.drive_time_remaining = 43200
        sync_state.photos_time_remaining = 3600

        sleep_for = sync._calculate_next_sync_schedule(config, sync_state)  # noqa: SLF001

        self.assertEqual(sleep_for, 3600)
        self.assertFalse(sync_state.enable_sync_drive)
        self.assertTrue(sync_state.enable_sync_photos)
        self.assertEqual(sync_state.drive_time_remaining, 39600)

    def test_calculate_next_sync_schedule_skips_a_one_shot_service_that_has_run(self):
        """A one-shot service leaves a negative countdown behind; it must not
        become the sleep (``time.sleep(-1)`` raises) or be re-enabled."""
        config = {"drive": {"sync_interval": -1}, "photos": {"sync_interval": 300}}
        sync_state = sync.SyncState()
        sync_state.drive_time_remaining = -1
        sync_state.photos_time_remaining = 300

        sleep_for = sync._calculate_next_sync_schedule(config, sync_state)  # noqa: SLF001

        self.assertEqual(sleep_for, 300)
        self.assertFalse(sync_state.enable_sync_drive)
        self.assertTrue(sync_state.enable_sync_photos)
        self.assertEqual(sync_state.drive_time_remaining, -1)

        # Both one-shot and both done: nothing is due, and the sleep is not negative.
        sync_state.photos_time_remaining = -1
        self.assertEqual(sync._calculate_next_sync_schedule(config, sync_state), 0)  # noqa: SLF001
        self.assertFalse(sync_state.enable_sync_drive)
        self.assertFalse(sync_state.enable_sync_photos)

    def test_calculate_next_sync_schedule_drive_only(self):
        """Test scheduling when only drive is configured."""
        config = {
            "drive": {"sync_interval": 3600},  # 1 hour
        }

        sync_state = sync.SyncState()
        sync_state.drive_time_remaining = 1800  # 30 min remaining

        sleep_for = sync._calculate_next_sync_schedule(config, sync_state)  # noqa: SLF001

        self.assertEqual(sleep_for, 1800, "Should sleep for drive remaining time")
        self.assertTrue(sync_state.enable_sync_drive, "Drive sync should be enabled")
        self.assertFalse(sync_state.enable_sync_photos, "Photos sync should be disabled")

    def test_calculate_next_sync_schedule_photos_only(self):
        """Test scheduling when only photos is configured."""
        config = {
            "photos": {"sync_interval": 3600},  # 1 hour
        }

        sync_state = sync.SyncState()
        sync_state.photos_time_remaining = 1800  # 30 min remaining

        sleep_for = sync._calculate_next_sync_schedule(config, sync_state)  # noqa: SLF001

        self.assertEqual(sleep_for, 1800, "Should sleep for photos remaining time")
        self.assertFalse(sync_state.enable_sync_drive, "Drive sync should be disabled")
        self.assertTrue(sync_state.enable_sync_photos, "Photos sync should be enabled")

    def test_calculate_next_sync_schedule_equal_zero_timers(self):
        """Test scheduling when both timers are 0 (initial state)."""
        config = {
            "drive": {"sync_interval": 86400},  # 24 hours
            "photos": {"sync_interval": 86400},  # 24 hours
        }

        # Simulate initial state where both timers are 0
        sync_state = sync.SyncState()
        sync_state.drive_time_remaining = 0
        sync_state.photos_time_remaining = 0

        sleep_for = sync._calculate_next_sync_schedule(config, sync_state)  # noqa: SLF001

        # Should have 0 sleep (immediate sync) but only drive should be enabled
        self.assertEqual(sleep_for, 0, "Should have immediate sync when both timers are 0")
        self.assertTrue(sync_state.enable_sync_drive, "Drive sync should be enabled")
        self.assertTrue(sync_state.enable_sync_photos, "Photos is due too, so it syncs in the same pass")

    def test_calculate_next_sync_schedule_equal_small_timers(self):
        """Test scheduling when both timers are equal but small (≤ 10 seconds)."""
        config = {
            "drive": {"sync_interval": 5},  # 5 seconds
            "photos": {"sync_interval": 5},  # 5 seconds
        }

        # Simulate state where both have small equal timers
        sync_state = sync.SyncState()
        sync_state.drive_time_remaining = 5
        sync_state.photos_time_remaining = 5

        sleep_for = sync._calculate_next_sync_schedule(config, sync_state)  # noqa: SLF001

        self.assertEqual(sleep_for, 5, "Should wait until both are due")
        self.assertTrue(sync_state.enable_sync_drive, "Drive sync should be enabled")
        self.assertTrue(sync_state.enable_sync_photos, "Photos sync should be enabled")

    @patch("src.sync.sleep")
    @patch("src.sync.notify.send", return_value=None)
    @patch("src.web_signals.record_auth_method")
    def test_a_security_key_account_skips_the_push_and_the_listener(
        self, _mock_record, mock_notify, _mock_sleep,
    ):
        """Apple issues no code for such an account, so requesting a push sends
        nothing and listening for a replied code waits for something that can
        never arrive. Both must be suppressed, and the log must say why."""
        sync_state = sync.SyncState()
        api = Mock()
        api.security_key_challenge = {"challenge": "abc", "keyHandles": ["k"]}

        with patch("src.sync._wait_for_telegram_code") as wait:
            with patch(
                "src.config_parser.get_telegram_listen_enabled", return_value=True,
            ):
                with self.assertLogs(level="ERROR") as captured:
                    self.assertTrue(self._run_2fa_handler(sync_state, api))

        api.trigger_2fa_push_notification.assert_not_called()
        wait.assert_not_called()
        # Nor may Telegram tell it to reply "auth" for a code.
        self.assertIs(mock_notify.call_args.kwargs["reply_prompt"], False)
        self.assertTrue(
            any("signs in with a security key" in e for e in captured.output),
        )


class TestWebSignalsSyncIntegration(unittest.TestCase):
    """Cover sync.sync() ↔ web_signals integration paths.
    Existing tests don't exercise the consume_force_sync TRUE branches
    or the record_sync_completion exception fallback."""

    def setUp(self):
        config = read_config(config_path=tests.CONFIG_PATH)
        assert isinstance(config, dict)
        self.config = config
        self.config["app"]["root"] = tests.TEMP_DIR
        os.makedirs(tests.TEMP_DIR, exist_ok=True)

    def tearDown(self):
        if os.path.exists(tests.TEMP_DIR):
            shutil.rmtree(tests.TEMP_DIR)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username",
        return_value=data.AUTHENTICATED_USER,
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_consume_force_sync_logs_when_signals_present(
        self,
        _mock_post,
        mock_read_config,
        _mock_service,
        _mock_un,
        _mock_pw,
    ):
        """consume_force_sync returns True for both drive + photos →
        each is logged as a force-sync request before the cycle runs."""
        import logging

        from src import web_signals

        cfg = deepcopy(self.config)
        mock_read_config.return_value = cfg
        os.environ.pop(ENV_ICLOUD_PASSWORD_KEY, None)

        calls = {"drive": 0, "photos": 0}

        def fake_consume(service):
            calls[service] += 1
            return calls[service] == 1

        with (
            patch.object(
                web_signals,
                "consume_force_sync",
                side_effect=fake_consume,
            ),
            self.assertLogs(sync.LOGGER, level=logging.INFO) as cm,
        ):
            sync.sync()

        joined = "\n".join(cm.output)
        self.assertIn("Force-sync requested for Drive", joined)
        self.assertIn("Force-sync requested for Photos", joined)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username",
        return_value=data.AUTHENTICATED_USER,
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_record_sync_completion_exception_is_logged_not_fatal(
        self,
        _mock_post,
        mock_read_config,
        _mock_service,
        _mock_un,
        _mock_pw,
    ):
        """record_sync_completion raising an unexpected exception (not
        ImportError) is logged at DEBUG and the sync loop continues."""
        import logging

        from src import web_signals

        cfg = deepcopy(self.config)
        mock_read_config.return_value = cfg
        os.environ.pop(ENV_ICLOUD_PASSWORD_KEY, None)

        # Force ``drive_stats`` non-None so the ``record_sync_completion``
        # branch is guaranteed to execute -- otherwise the mock chain can
        # leave both stats None, the call never happens, and the assertion
        # below would pass without ever exercising the path under test.
        with (
            patch(
                "src.sync._perform_drive_sync",
                return_value=DriveStats(files_downloaded=1),
            ) as mock_drive,
            patch.object(
                web_signals,
                "record_sync_completion",
                side_effect=RuntimeError("disk full"),
            ) as mock_record,
            self.assertLogs(sync.LOGGER, level=logging.DEBUG) as cm,
        ):
            sync.sync()

        # The branch really ran ...
        self.assertTrue(mock_drive.called)
        self.assertTrue(mock_record.called)
        # ... the raise was swallowed to DEBUG ...
        joined = "\n".join(cm.output)
        self.assertIn("record_sync_completion raised", joined)
        self.assertIn("disk full", joined)


class TestInterruptibleSleep(unittest.TestCase):
    """``_interruptible_sleep`` chunks long sleeps and polls the
    web-signal sentinels so the "Sync now" button feels responsive
    even mid-multi-hour interval."""

    def test_short_interval_uses_single_sleep_call(self):
        """``<= _CHUNK`` should produce exactly one ``sleep`` call so
        existing tests counting sleep invocations stay correct."""
        from unittest.mock import patch

        with patch("src.sync.sleep") as mock_sleep:
            sync._interruptible_sleep(2)  # noqa: SLF001 -- module-private helper
        mock_sleep.assert_called_once_with(2)

    def test_long_interval_chunks_and_polls_sentinels(self):
        """``> _CHUNK`` should produce multiple sleep calls AND call
        ``pending_force_syncs()`` between each chunk."""
        from unittest.mock import patch

        with (
            patch("src.sync.sleep") as mock_sleep,
            patch(
                "src.web_signals.pending_force_syncs",
                return_value=[],
            ) as mock_pending,
        ):
            sync._interruptible_sleep(5)  # noqa: SLF001
        # Expect [sleep(2), sleep(2), sleep(1)] -- 3 calls.
        self.assertEqual(mock_sleep.call_count, 3)
        self.assertEqual(mock_pending.call_count, 3)

    def test_long_interval_returns_early_when_sentinel_fires(self):
        """If ``pending_force_syncs`` reports any sentinel mid-loop,
        the helper exits without consuming the remaining chunks."""
        from unittest.mock import patch

        with (
            patch("src.sync.sleep") as mock_sleep,
            patch(
                "src.web_signals.pending_force_syncs",
                side_effect=[[], ["drive"]],
            ) as mock_pending,
        ):
            sync._interruptible_sleep(10)  # noqa: SLF001
        # Exited after the second chunk -> 2 sleeps + 2 polls.
        self.assertEqual(mock_sleep.call_count, 2)
        self.assertEqual(mock_pending.call_count, 2)



class TestACompletedReauthEndsTheRetryWait(unittest.TestCase):
    """The loop backs off for retry_login_interval between sign-in attempts
    and cannot otherwise see that the session was fixed underneath it, so
    someone who signs in through the web UI watches the dashboard keep
    reporting the sync as stopped until an interval that began before the
    problem was solved finally runs out."""

    def test_a_completed_reauth_ends_the_wait(self):
        from unittest.mock import patch

        from src import sync

        with patch.object(sync, "sleep") as slept:
            with patch("src.web_signals.consume_reauth_completed", return_value=True):
                sync._auth_retry_sleep(600)  # noqa: SLF001
        self.assertLess(sum(c.args[0] for c in slept.call_args_list), 600)

    def test_without_a_reauth_the_whole_interval_is_served(self):
        from unittest.mock import patch

        from src import sync

        with patch.object(sync, "sleep") as slept:
            with patch("src.web_signals.consume_reauth_completed", return_value=False):
                sync._auth_retry_sleep(10)  # noqa: SLF001
        self.assertEqual(sum(c.args[0] for c in slept.call_args_list), 10)

    def test_a_force_sync_request_does_not_end_an_auth_wait(self):
        """"Sync now" means sync everything now, not "stop waiting to sign
        in" -- borrowing it would queue a full re-enumeration nobody asked
        for, and on a rate-limited account it would drive sign-in attempts."""
        from unittest.mock import patch

        from src import sync

        with patch.object(sync, "sleep") as slept:
            with patch("src.web_signals.pending_force_syncs", return_value=["drive"]):
                with patch(
                    "src.web_signals.consume_reauth_completed", return_value=False,
                ):
                    sync._auth_retry_sleep(10)  # noqa: SLF001
        self.assertEqual(sum(c.args[0] for c in slept.call_args_list), 10)

    def test_a_short_wait_is_a_single_sleep(self):
        from unittest.mock import patch

        from src import sync

        with patch.object(sync, "sleep") as slept:
            sync._auth_retry_sleep(1)  # noqa: SLF001
        slept.assert_called_once_with(1)

    def test_a_successful_reauth_signals_the_loop(self):
        from unittest.mock import patch

        from src import web

        with patch("src.web.web_signals.record_reauth_completed") as rec:
            with patch("src.web.web_signals.request_force_sync") as force:
                web._wake_sync_loop()  # noqa: SLF001
        rec.assert_called_once_with()
        force.assert_not_called()

    def test_a_failed_signal_never_fails_the_sign_in(self):
        from unittest.mock import patch

        from src import web

        with patch(
            "src.web.web_signals.record_reauth_completed",
            side_effect=OSError("read-only"),
        ):
            web._wake_sync_loop()  # noqa: SLF001


    def test_the_2fa_handler_reports_keep_going(self):
        """Returning True is what sends the loop round again rather than
        ending it -- the retry path must not look like a fatal error."""
        from unittest.mock import MagicMock, patch

        from src import sync

        config = {"app": {"credentials": {"retry_login_interval": 600}}}
        with patch.object(sync, "_auth_retry_sleep"):
            with patch.object(sync, "notify"):
                self.assertTrue(
                    sync._handle_2fa_required(  # noqa: SLF001
                        config, "a@icloud.com", sync.SyncState(), MagicMock(),
                    ),
                )

    def test_the_password_handler_reports_keep_going(self):
        from unittest.mock import patch

        from src import sync

        config = {"app": {"credentials": {"retry_login_interval": 600}}}
        with patch.object(sync, "_auth_retry_sleep"):
            with patch.object(sync, "notify"):
                self.assertTrue(
                    sync._handle_password_error(  # noqa: SLF001
                        config,
                        "a@icloud.com",
                        sync.SyncState(),
                        exceptions.ICloudPyNoStoredPasswordAvailableException("no saved session"),
                    ),
                )

    def _loop_once_then_exit(self, **auth_kwargs):
        """Drive sync() so a handler runs, the loop continues, and the second
        retry wait ends the test -- proving the loop retried rather than
        exiting."""
        from unittest.mock import patch

        from src import sync

        config = {
            "app": {
                "credentials": {
                    "username": "a@icloud.com",
                    "retry_login_interval": 600,
                },
            },
            "drive": {"destination": "drive"},
        }
        with (
            patch.object(sync, "_load_configuration", return_value=config),
            patch.object(sync, "alive"),
            patch.object(sync, "notify"),
            patch.object(sync, "_authenticate_and_get_api", **auth_kwargs),
            patch.object(
                sync, "_auth_retry_sleep", side_effect=[None, SystemExit],
            ) as slept,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            with self.assertRaises(SystemExit):
                sync.sync()
        return slept

    def test_a_pending_second_factor_sends_the_loop_round_again(self):
        from unittest.mock import MagicMock

        api = MagicMock()
        api.requires_2sa = True
        slept = self._loop_once_then_exit(return_value=api)
        self.assertEqual(slept.call_count, 2)

    def test_a_missing_keyring_password_sends_the_loop_round_again(self):
        from icloudpy import exceptions

        slept = self._loop_once_then_exit(
            side_effect=exceptions.ICloudPyNoStoredPasswordAvailableException(),
        )
        self.assertEqual(slept.call_count, 2)



class TestRevocationIsNamedSeparatelyFromExpiry(unittest.TestCase):
    """Expiry and revocation both surface as 421 and both end in a 2FA
    prompt, but a refresh schedule prevents one and can do nothing about the
    other. Without saying which happened, the obvious reading of "valid trust
    token, 2FA demanded anyway" is that the refresh logic is broken."""

    def test_a_still_valid_token_is_reported_as_revoked(self):
        import datetime
        from unittest.mock import MagicMock, patch

        from src.sync import _log_trust_revocation_hint

        future = datetime.datetime.now(
            tz=datetime.timezone.utc,
        ) + datetime.timedelta(days=58)
        with patch("src.sync._read_trust_cookie_expiry", return_value=future):
            with self.assertLogs(level="ERROR") as captured:
                _log_trust_revocation_hint(MagicMock())
        joined = "\n".join(captured.output)
        self.assertIn("had not expired", joined)
        self.assertIn("revoked it", joined)
        # A day count, not a specific one: timedelta.days truncates, so
        # "+58 days from now" reads back as 57 and pinning the number makes
        # the test fail on arithmetic rather than on behaviour.
        self.assertRegex(joined, r"valid for \d+ more days")

    def test_an_actually_expired_token_says_nothing(self):
        """Ordinary expiry is not news -- the 2FA prompt already says it."""
        import datetime
        import logging
        from unittest.mock import MagicMock, patch

        from src.sync import _log_trust_revocation_hint

        past = datetime.datetime.now(
            tz=datetime.timezone.utc,
        ) - datetime.timedelta(days=1)
        with patch("src.sync._read_trust_cookie_expiry", return_value=past):
            with patch.object(logging.getLogger(), "error") as err:
                _log_trust_revocation_hint(MagicMock())
        err.assert_not_called()

    def test_no_trust_cookie_says_nothing(self):
        import logging
        from unittest.mock import MagicMock, patch

        from src.sync import _log_trust_revocation_hint

        with patch("src.sync._read_trust_cookie_expiry", return_value=None):
            with patch.object(logging.getLogger(), "error") as err:
                _log_trust_revocation_hint(MagicMock())
        err.assert_not_called()

    def test_a_raising_reader_never_breaks_the_retry(self):
        from unittest.mock import MagicMock, patch

        from src.sync import _log_trust_revocation_hint

        with patch(
            "src.sync._read_trust_cookie_expiry",
            side_effect=RuntimeError("cookie jar gone"),
        ):
            _log_trust_revocation_hint(MagicMock())  # must not raise


class TestSigninTransportFailures(unittest.TestCase):
    """A sign-in failure Apple does not express as a 2FA prompt must not
    end the process.

    Only the missing-password exception was caught, so a bare requests
    HTTPError from ICloudPyService construction escaped, exited, and -- with
    the container's restart policy -- became a loop that re-authenticated
    every few seconds. Apple answers a rate-limited account with 409 on
    /signin/init, so the loop was hammering the very condition it was
    reacting to."""

    def test_backoff_floor_beats_a_short_retry_interval(self):
        from unittest.mock import MagicMock, patch

        from src import sync

        config = {"app": {"credentials": {"retry_login_interval": 60}}}
        with patch.object(sync, "_auth_retry_sleep") as slept:
            keep_going = sync._handle_auth_transport_error(  # noqa: SLF001
                config,
                "a@icloud.com",
                MagicMock(),
                RuntimeError("409"),
            )
        self.assertTrue(keep_going)
        self.assertGreaterEqual(
            slept.call_args.args[0],
            sync._AUTH_BACKOFF_FLOOR_SEC,  # noqa: SLF001
        )

    def test_negative_interval_exits(self):
        from unittest.mock import MagicMock

        from src import sync

        config = {"app": {"credentials": {"retry_login_interval": -1}}}
        self.assertFalse(
            sync._handle_auth_transport_error(  # noqa: SLF001
                config,
                "a@icloud.com",
                MagicMock(),
                RuntimeError("409"),
            ),
        )

    def test_loop_retries_after_a_recoverable_failure(self):
        """The continue path: the handler says keep going, the loop loops."""
        from unittest.mock import patch

        import requests

        from src import sync

        config = {
            "app": {"credentials": {"username": "a@icloud.com"}},
            "drive": {"destination": "drive"},
        }
        with (
            patch.object(sync, "_load_configuration", return_value=config),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(
                sync,
                "_authenticate_and_get_api",
                side_effect=requests.exceptions.HTTPError("409 Client Error"),
            ),
            patch.object(
                sync,
                "_handle_auth_transport_error",
                side_effect=[True, False],
            ) as handler,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            sync.sync()
        self.assertEqual(handler.call_count, 2)

    def test_http_error_is_a_request_exception(self):
        """Guard the except clause: the crash was an HTTPError, so the
        handler only helps if that type is actually caught."""
        import requests

        self.assertTrue(
            issubclass(
                requests.exceptions.HTTPError,
                requests.exceptions.RequestException,
            ),
        )

    def test_loop_absorbs_an_http_error_instead_of_dying(self):
        from unittest.mock import patch

        import requests

        from src import sync

        config = {
            "app": {
                "credentials": {"username": "a@icloud.com", "retry_login_interval": -1},
            },
            "drive": {"destination": "drive"},
        }
        with (
            patch.object(sync, "_load_configuration", return_value=config),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(
                sync,
                "_authenticate_and_get_api",
                side_effect=requests.exceptions.HTTPError("409 Client Error"),
            ),
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            sync.sync()  # must return, not raise


class TestServiceUnavailableIsNotASigninFailure(unittest.TestCase):
    """A zone or service being unavailable says nothing about the sign-in.

    ICloudPyServiceNotActivatedException subclasses
    ICloudPyAPIResponseException, so catching the parent to absorb sign-in
    faults also swallows "Zone does not exist" -- which then earns the
    rate-limit backoff for an account that is signed in perfectly well."""

    def test_it_is_a_subclass_of_the_broader_exception(self):
        """The reason the broad catch swallows it."""
        from icloudpy import exceptions

        self.assertTrue(
            issubclass(
                exceptions.ICloudPyServiceNotActivatedException,
                exceptions.ICloudPyAPIResponseException,
            ),
        )

    def test_zone_errors_use_the_ordinary_interval(self):
        from unittest.mock import patch

        from icloudpy import exceptions

        from src import sync

        config = {
            "app": {"credentials": {"username": "a@icloud.com", "retry_login_interval": -1}},
            "drive": {"destination": "drive"},
        }
        error = exceptions.ICloudPyServiceNotActivatedException("Zone does not exist")
        with (
            patch.object(sync, "_load_configuration", return_value=config),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(sync, "_authenticate_and_get_api", side_effect=error),
            patch.object(sync, "_handle_auth_transport_error") as auth_handler,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            sync.sync()
        auth_handler.assert_not_called()

    def test_zone_errors_wait_and_retry(self):
        """Not fatal: the account is fine, the service is not."""
        from unittest.mock import patch

        from icloudpy import exceptions

        from src import sync

        config = {
            "app": {"credentials": {"username": "a@icloud.com"}},
            "drive": {"destination": "drive"},
        }
        error = exceptions.ICloudPyServiceNotActivatedException("Zone does not exist")
        with (
            patch.object(sync, "_load_configuration", return_value=config),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(sync, "_authenticate_and_get_api", side_effect=error),
            patch.object(sync, "_interruptible_sleep", side_effect=[None, SystemExit]) as slept,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            with self.assertRaises(SystemExit):
                sync.sync()
        self.assertGreaterEqual(slept.call_count, 1)


class TestPostAuthFailuresAreNotSigninFailures(unittest.TestCase):
    """Errors raised once ``api`` exists are service faults, not auth faults.

    The sync loop wraps authentication and the whole sync in one ``try``, so
    without routing on "did we get past sign-in" a 5xx on a photo download is
    reported to the user as a sign-in failure and earns the rate-limit
    backoff. Worse, every handler ends in ``continue``, which skips
    ``_calculate_next_sync_schedule`` -- the countdown timers never advance,
    so the short login-retry interval re-enumerates the entire library."""

    def _config(self, retry=600, drive_interval=43200):
        return {
            "app": {"credentials": {"username": "a@icloud.com", "retry_login_interval": retry}},
            "drive": {"destination": "drive", "sync_interval": drive_interval},
        }

    def test_failure_after_signin_does_not_use_the_auth_backoff(self):
        from unittest.mock import MagicMock, patch

        from icloudpy import exceptions

        from src import sync

        api = MagicMock()
        api.requires_2sa = False
        error = exceptions.ICloudPyAPIResponseException("500 Server Error")
        with (
            patch.object(sync, "_load_configuration", return_value=self._config(retry=-1)),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(sync, "_authenticate_and_get_api", return_value=api),
            patch.object(sync, "_maybe_warn_trust_expiring"),
            patch.object(sync, "_perform_drive_sync", side_effect=error),
            patch.object(sync, "_handle_auth_transport_error") as auth_handler,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            sync.sync()
        auth_handler.assert_not_called()

    def test_failure_before_signin_still_uses_the_auth_backoff(self):
        """The throttle case must keep its long floor."""
        from unittest.mock import patch

        from icloudpy import exceptions

        from src import sync

        error = exceptions.ICloudPyAPIResponseException("409 Conflict")
        with (
            patch.object(sync, "_load_configuration", return_value=self._config()),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(sync, "_authenticate_and_get_api", side_effect=error),
            patch.object(sync, "_handle_auth_transport_error", return_value=False) as auth_handler,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            sync.sync()
        auth_handler.assert_called_once()

    def test_retry_never_polls_faster_than_the_sync_interval(self):
        """A broken service must not be polled faster than a working one."""
        from unittest.mock import patch

        from src import sync

        with patch.object(sync, "_interruptible_sleep") as slept:
            kept_looping = sync._handle_sync_error(  # noqa: SLF001
                self._config(retry=600, drive_interval=43200),
                Exception("boom"),
                43200,
                -1,
            )
        self.assertTrue(kept_looping)
        slept.assert_called_once_with(43200)

    def test_a_sync_retry_is_not_announced_as_a_login_retry(self):
        """Both halves of the old message: the interval getter announced
        "Retrying login every N seconds." and the handler then announced
        "Retrying login at ...", for a sync that failed after sign-in."""
        from unittest.mock import patch

        from src import sync

        with patch.object(sync, "_interruptible_sleep"), self.assertLogs(level="INFO") as logs:
            sync._handle_sync_error(self._config(), Exception("boom"), 43200, -1)  # noqa: SLF001
        self.assertTrue(any("Retrying sync at" in line for line in logs.output))
        self.assertFalse(any("Retrying login" in line for line in logs.output))

    def test_retry_falls_back_to_the_login_interval_when_nothing_is_configured(self):
        from unittest.mock import patch

        from src import sync

        with patch.object(sync, "_interruptible_sleep") as slept:
            sync._handle_sync_error(  # noqa: SLF001
                self._config(retry=600), Exception("boom"), -1, -1,
            )
        slept.assert_called_once_with(600)

    def test_negative_retry_interval_exits(self):
        from src import sync

        self.assertFalse(
            sync._handle_sync_error(  # noqa: SLF001
                self._config(retry=-1), Exception("boom"), 43200, -1,
            ),
        )
    def test_the_loop_continues_after_a_post_signin_failure(self):
        """A service fault is retried, not fatal: the daemon keeps running."""
        from unittest.mock import MagicMock, patch

        from icloudpy import exceptions

        from src import sync

        api = MagicMock()
        api.requires_2sa = False
        error = exceptions.ICloudPyAPIResponseException("500 Server Error")
        with (
            patch.object(sync, "_load_configuration", return_value=self._config()),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(sync, "_authenticate_and_get_api", return_value=api),
            patch.object(sync, "_maybe_warn_trust_expiring"),
            patch.object(sync, "_perform_drive_sync", side_effect=error),
            # True keeps the loop alive for a second pass, False ends the test.
            patch.object(sync, "_handle_sync_error", side_effect=[True, False]) as handler,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            sync.sync()
        self.assertEqual(handler.call_count, 2)


class TestUnreadableConfigDoesNotKillTheDaemon(unittest.TestCase):
    """A missing or half-written config.yaml must not become a restart loop.

    On a NAS the volume holding the config can lag behind container start or
    vanish mid-run. ``read_config`` returns None for a missing file, and the
    downstream ``"drive" not in config`` raised TypeError straight out of the
    loop -- which ``restart: unless-stopped`` turns into a crash loop."""

    def test_missing_config_waits_instead_of_raising(self):
        from unittest.mock import patch

        from src import sync

        # Second pass returns a config whose intervals are negative so the
        # loop exits; the first pass is the one under test.
        configs = [None, {"app": {"credentials": {"username": None}}}]
        with (
            patch.object(sync, "_load_configuration", side_effect=configs),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(sync, "sleep") as slept,
            patch.object(sync, "_interruptible_sleep"),
            patch("src.config_parser.get_username", return_value=None),
        ):
            sync.sync()
        slept.assert_called_once_with(600)

    def test_unparseable_config_waits_instead_of_raising(self):
        from unittest.mock import patch

        from src import sync

        side_effects = [
            ValueError("could not parse yaml"),
            {"app": {"credentials": {"username": None}}},
        ]
        with (
            patch.object(sync, "_load_configuration", side_effect=side_effects),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(sync, "sleep") as slept,
            patch.object(sync, "_interruptible_sleep"),
            patch("src.config_parser.get_username", return_value=None),
        ):
            sync.sync()
        slept.assert_called_once_with(600)

    def test_dry_run_returns_instead_of_waiting(self):
        from unittest.mock import patch

        from src import sync

        with (
            patch.object(sync, "_load_configuration", return_value=None),
            patch.object(sync, "sleep") as slept,
        ):
            sync.sync(dry_run=True)
        slept.assert_not_called()


class TestStaleLibraryStateCleanupIsBestEffort(unittest.TestCase):
    """Clearing dashboard state is never worth blocking startup over."""

    def test_a_failure_clearing_state_does_not_stop_the_loop(self):
        from unittest.mock import patch

        from src import sync, web_signals

        config = {
            "app": {"credentials": {"username": None, "retry_login_interval": -1}},
        }
        with (
            patch.object(sync, "_load_configuration", return_value=config),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(
                web_signals,
                "clear_stale_library_states",
                side_effect=OSError("read-only fs"),
            ),
            patch.object(sync, "_interruptible_sleep"),
            patch("src.config_parser.get_username", return_value=None),
        ):
            sync.sync()


class TestSecurityKeyAccountsSkipTheCodeFlow(unittest.TestCase):
    """Once security keys are enrolled Apple stops issuing 6-digit codes, so
    requesting a push sends nothing and listening for a replied code waits for
    something that cannot arrive. Both ran every cycle, and Telegram told the
    user to reply a code that Apple would never send."""

    def test_a_pending_challenge_is_detected_and_recorded(self):
        from unittest.mock import MagicMock, patch

        from src.sync import _detect_security_key_account

        api = MagicMock()
        api.security_key_challenge = {"challenge": "abc", "keyHandles": ["k"]}
        with patch("src.web_signals.record_auth_method") as record:
            self.assertTrue(_detect_security_key_account(api, "a@b.com"))
        record.assert_called_once_with(username="a@b.com", method="security_key")

    def test_no_challenge_means_the_ordinary_code_flow(self):
        from unittest.mock import MagicMock

        from src.sync import _detect_security_key_account

        api = MagicMock()
        api.security_key_challenge = None
        self.assertFalse(_detect_security_key_account(api, "a@b.com"))

    def test_icloudpy_without_security_key_support_is_not_an_error(self):
        from src.sync import _detect_security_key_account

        class Old:
            """No security_key_challenge attribute at all."""

        self.assertFalse(_detect_security_key_account(Old(), "a@b.com"))

    def test_a_probe_that_raises_does_not_break_the_retry_loop(self):
        from src.sync import _detect_security_key_account

        class Boom:
            @property
            def security_key_challenge(self):
                msg = "apple said no"
                raise RuntimeError(msg)

        self.assertFalse(_detect_security_key_account(Boom(), "a@b.com"))

    def test_recording_failure_still_reports_the_security_key(self):
        """Wording is not worth losing the suppression that matters."""
        from unittest.mock import MagicMock, patch

        from src.sync import _detect_security_key_account

        api = MagicMock()
        api.security_key_challenge = {"challenge": "abc", "keyHandles": ["k"]}
        with patch(
            "src.web_signals.record_auth_method",
            side_effect=OSError("read-only fs"),
        ):
            self.assertTrue(_detect_security_key_account(api, "a@b.com"))


class TestSigninFailuresThroughTheRealIcloudpyPath(unittest.TestCase):
    """icloudpy wraps most sign-in errors in ICloudPyFailedLoginException,
    which subclasses ICloudPyException directly -- not the API-response or
    requests classes the loop caught. Earlier tests raised those classes
    straight from a patched _authenticate_and_get_api, skipping the wrap, so
    a 409-with-reason, a 5xx or a rejected password still exited the process
    and, under restart: unless-stopped, became a sign-in crash loop.

    These drive the real ICloudPyService against a faked HTTP layer, so the
    exception the loop sees is the one icloudpy actually raises."""

    def _apple_says(self, status, body):
        import json

        import requests

        def fake(_session, method, url, **_kw):
            response = requests.Response()
            response.status_code = status
            response.url = url
            response.reason = "error"
            response._content = json.dumps(body).encode()  # noqa: SLF001
            response.headers["Content-Type"] = "application/json"
            return response

        return fake

    def _run_loop(self, status, body):
        from unittest.mock import patch

        from src import sync

        config = {
            "app": {"credentials": {"username": "a@icloud.com", "retry_login_interval": 600}},
            "drive": {"destination": "drive"},
        }
        with (
            patch.object(sync, "_load_configuration", return_value=config),
            patch.object(sync, "alive"),
            patch.object(sync, "notify") as notify,
            patch.object(sync, "_retrieve_password", return_value="pw"),
            patch("requests.Session.request", self._apple_says(status, body)),
            patch.object(sync, "_auth_retry_sleep", side_effect=[None, SystemExit]) as slept,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            with self.assertRaises(SystemExit):
                sync.sync()
        return slept, notify

    def test_every_sign_in_error_shape_is_retried_not_fatal(self):
        cases = [
            (409, {"reason": "Too many attempts"}),
            (500, {}),
            (503, {"errorMessage": "Service Unavailable"}),
            (401, {"errorMessage": "Invalid credentials"}),
            (409, {"serviceErrors": [{"code": "-20209"}]}),
        ]
        from src import sync

        for status, body in cases:
            with self.subTest(status=status, body=body):
                slept, _ = self._run_loop(status, body)
                # Reached the second wait: the loop retried instead of exiting.
                self.assertEqual(slept.call_count, 2)
                # And waited at least the throttle floor, never the short interval.
                self.assertGreaterEqual(
                    slept.call_args_list[0].args[0],
                    sync._AUTH_BACKOFF_FLOOR_SEC,  # noqa: SLF001
                )

    def test_a_negative_retry_interval_still_exits_cleanly(self):
        """retry_login_interval < 0 is the documented way to ask for an exit
        instead of a retry; that must keep working for this error too."""
        from unittest.mock import patch

        from src import sync

        config = {
            "app": {"credentials": {"username": "a@icloud.com", "retry_login_interval": -1}},
            "drive": {"destination": "drive"},
        }
        with (
            patch.object(sync, "_load_configuration", return_value=config),
            patch.object(sync, "alive"),
            patch.object(sync, "notify"),
            patch.object(sync, "_retrieve_password", return_value="pw"),
            patch("requests.Session.request", self._apple_says(500, {})),
            patch.object(sync, "_auth_retry_sleep") as slept,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            sync.sync()  # returns rather than raising or looping
        slept.assert_not_called()

    def test_a_rejected_sign_in_tells_the_user(self):
        """A wrong password raises the same exception and never heals by
        retrying, so the user has to be told -- notify.send is throttled."""
        _, notify = self._run_loop(401, {"errorMessage": "Invalid credentials"})
        notify.send.assert_called()


class TestSyncingWithoutAStoredPassword(unittest.TestCase):
    """An operator may prefer not to keep an Apple ID password on disk --
    on a headless container `keyring` degrades to a plaintext file -- and
    run unattended off the saved session alone until Apple's trust window
    closes. The loop used to refuse before it ever looked at the session."""

    def _session_only_client(self, session_data):
        """A client with its ``__init__`` skipped.

        ``ICloudPyService.__init__`` authenticates as its last act, which is
        the very thing under test here, so the instance is built around the
        state ``authenticate`` reads instead.
        """
        api = sync.SessionOnlyICloudPyService.__new__(sync.SessionOnlyICloudPyService)
        api.session_data = session_data
        api.session = Mock()
        return api

    def test_a_valid_session_authenticates_with_no_password_at_all(self):
        api = self._session_only_client({"session_token": "token"})
        with patch.object(
            sync.SessionOnlyICloudPyService,
            "_validate_token",
            return_value={"webservices": {"drivews": {}}},
        ):
            api.authenticate()
        self.assertEqual(api._webservices, {"drivews": {}})  # noqa: SLF001
        # Nothing was posted to Apple's sign-in endpoint.
        api.session.post.assert_not_called()

    def test_no_session_is_reported_rather_than_signed_in_for(self):
        api = self._session_only_client({})
        with self.assertRaises(exceptions.ICloudPyNoStoredPasswordAvailableException) as raised:
            api.authenticate()
        self.assertIn("no saved session", str(raised.exception))
        api.session.post.assert_not_called()

    def test_an_invalid_session_is_reported_rather_than_signed_in_for(self):
        """The upstream fallback would post the placeholder password to
        Apple's sign-in endpoint on every retry, which is the fastest way
        to get an Apple ID throttled."""
        for code in sorted(sync._SESSION_REJECTED_CODES):  # noqa: SLF001
            with self.subTest(code=code):
                api = self._session_only_client({"session_token": "stale"})
                with (
                    patch.object(
                        sync.SessionOnlyICloudPyService,
                        "_validate_token",
                        side_effect=exceptions.ICloudPyAPIResponseException(
                            "Authentication required for Account.", code,
                        ),
                    ),
                    self.assertRaises(exceptions.ICloudPyNoStoredPasswordAvailableException) as raised,
                ):
                    api.authenticate()
                self.assertIn("no longer valid", str(raised.exception))
                api.session.post.assert_not_called()

    def test_an_outage_is_not_reported_as_an_expired_session(self):
        """A 5xx leaves the session perfectly good. Reporting it as expired
        would send the user off to re-authenticate for nothing, so it stays
        an API error and reaches the loop's transport handler instead."""
        api = self._session_only_client({"session_token": "token"})
        with (
            patch.object(
                sync.SessionOnlyICloudPyService,
                "_validate_token",
                side_effect=exceptions.ICloudPyAPIResponseException("Service Unavailable", 503),
            ),
            self.assertRaises(exceptions.ICloudPyAPIResponseException) as raised,
        ):
            api.authenticate()
        self.assertEqual(raised.exception.code, 503)
        api.session.post.assert_not_called()

    def test_a_validate_body_without_webservices_does_not_kill_the_process(self):
        """icloudpy returns the response untouched when a failed /validate
        carries no recognised error field, so ``data`` can be an error body.
        Upstream indexes it and raises KeyError, which escapes the loop and
        -- under `restart: unless-stopped` -- becomes a restart loop."""
        api = self._session_only_client({"session_token": "token"})
        with (
            patch.object(
                sync.SessionOnlyICloudPyService,
                "_validate_token",
                return_value={"errorMessage": "something else entirely"},
            ),
            self.assertRaises(exceptions.ICloudPyNoStoredPasswordAvailableException),
        ):
            api.authenticate()

    def test_a_forced_refresh_is_refused(self):
        """Defence in depth. Nothing in this app asks for a forced refresh
        -- icloudpy's only caller is its Find My 450 handler, which is
        never reached here -- but honouring one would mean the credential
        sign-in this class exists to prevent, so it is refused wherever it
        came from."""
        api = self._session_only_client({"session_token": "token"})
        with self.assertRaises(exceptions.ICloudPyNoStoredPasswordAvailableException):
            api.authenticate(force_refresh=True)
        api.session.post.assert_not_called()

    def test_the_client_is_built_without_the_real_password_when_none_is_stored(self):
        with patch.object(sync, "SessionOnlyICloudPyService") as mock_class:
            sync.get_api_instance(username=data.AUTHENTICATED_USER, password=None)
        mock_class.assert_called_once()
        # icloudpy reads the keyring when handed ``None`` and redacts every
        # log line when handed ``""`` -- neither is acceptable here.
        placeholder = mock_class.call_args.kwargs["password"]
        self.assertTrue(placeholder)
        self.assertNotEqual(placeholder, data.VALID_PASSWORD)

    def test_the_china_region_is_session_only_too(self):
        with patch.object(sync, "SessionOnlyICloudPyService") as mock_class:
            sync.get_api_instance(
                username=data.AUTHENTICATED_USER,
                password=None,
                server_region="china",
            )
        self.assertIn(".com.cn", mock_class.call_args.kwargs["home_endpoint"])

    def test_a_stored_password_still_takes_the_ordinary_path(self):
        with patch.object(sync, "SessionOnlyICloudPyService") as mock_class:
            with patch("src.sync.ICloudPyService") as mock_ordinary:
                sync.get_api_instance(
                    username=data.AUTHENTICATED_USER,
                    password=data.VALID_PASSWORD,
                )
        mock_class.assert_not_called()
        self.assertEqual(mock_ordinary.call_args.kwargs["password"], data.VALID_PASSWORD)

    def test_a_missing_password_falls_through_to_the_session(self):
        with (
            patch.object(
                sync,
                "_retrieve_password",
                side_effect=exceptions.ICloudPyNoStoredPasswordAvailableException(),
            ),
            patch.object(sync, "get_api_instance") as mock_get_api,
            patch("src.config_parser.get_region", return_value="global"),
        ):
            sync._authenticate_and_get_api({}, data.AUTHENTICATED_USER)  # noqa: SLF001
        self.assertIsNone(mock_get_api.call_args.kwargs["password"])

    def test_a_blank_password_counts_as_no_password(self):
        """Compose turns an unset ${VAR} into "", which must select
        session-only mode -- not send an empty password to Apple's sign-in --
        and must not overwrite a stored password with it."""
        for keyring_value in (None, ""):
            with self.subTest(keyring=keyring_value):
                missing = exceptions.ICloudPyNoStoredPasswordAvailableException()
                with (
                    patch.dict(os.environ, {ENV_ICLOUD_PASSWORD_KEY: ""}),
                    patch.object(sync.utils, "store_password_in_keyring") as stored,
                    patch.object(
                        sync.utils,
                        "get_password_from_keyring",
                        side_effect=missing if keyring_value is None else None,
                        return_value=keyring_value,
                    ),
                    self.assertRaises(exceptions.ICloudPyNoStoredPasswordAvailableException),
                ):
                    sync._retrieve_password(data.AUTHENTICATED_USER)  # noqa: SLF001
                stored.assert_not_called()

    def test_a_blank_variable_does_not_hide_a_stored_password(self):
        with (
            patch.dict(os.environ, {ENV_ICLOUD_PASSWORD_KEY: ""}),
            patch.object(sync.utils, "store_password_in_keyring") as stored,
            patch.object(sync.utils, "get_password_from_keyring", return_value="stored"),
        ):
            self.assertEqual(sync._retrieve_password(data.AUTHENTICATED_USER), "stored")  # noqa: SLF001
        stored.assert_not_called()

    def test_the_error_says_what_to_do_and_tells_the_dashboard(self):
        """The old wording ("save the password in keyring") is the wrong
        instruction for a deliberately password-free setup: it is the
        session that has to be replaced."""
        error = exceptions.ICloudPyNoStoredPasswordAvailableException(
            "No Apple ID password is stored and the saved session is no longer valid.",
        )
        config = {"app": {"credentials": {"retry_login_interval": 600}}}
        with (
            patch.object(sync, "_auth_retry_sleep"),
            patch.object(sync, "notify"),
            patch.object(sync, "_publish_auth_blocked") as published,
            self.assertLogs(sync.LOGGER, level="ERROR") as captured,
        ):
            self.assertTrue(
                sync._handle_password_error(  # noqa: SLF001
                    config, data.AUTHENTICATED_USER, sync.SyncState(), error,
                ),
            )
        self.assertTrue(any("no longer valid" in line for line in captured.output))
        self.assertEqual(published.call_args.kwargs["reason"], "session_unusable")


    def _real_transport_session_only(self, validate_status, validate_body, content_type="application/json"):
        """Build a session-only client for real, with a session file on disk,
        a keyring that is fatal to consult, and a fake Apple that answers
        /validate as asked and records any request to the sign-in endpoint.

        Returns ``(api_or_None, raised_or_None, touched_signin)``.
        """
        import json
        import tempfile

        import requests

        touched_signin = []

        def fake_apple(_session, _method, url, **_kwargs):
            response = requests.Response()
            response.url = url
            if "/validate" in url:
                response.status_code = validate_status
                response.reason = "error"
                response.headers["Content-Type"] = content_type
                response._content = json.dumps(validate_body).encode()  # noqa: SLF001
                return response
            touched_signin.append(url)
            response.status_code = 500
            response.reason = "should never be reached"
            response.headers["Content-Type"] = "application/json"
            response._content = b"{}"  # noqa: SLF001
            return response

        api = raised = None
        with tempfile.TemporaryDirectory() as cookie_directory:
            with open(os.path.join(cookie_directory, "aicloudcom.session"), "w", encoding="utf-8") as handle:
                json.dump({"session_token": "saved-token"}, handle)
            with (
                # tests/data's ICloudPyServiceMock.__init__ assigns
                # ``base.ICloudPySession = ICloudPySessionMock`` and never puts
                # it back, so by the time the full suite reaches this test the
                # session class is process-wide swapped and answers from canned
                # fixtures instead of ``fake_apple``. ``__bases__[0]`` is the
                # genuine class, captured when the mock subclassed it.
                patch("icloudpy.base.ICloudPySession", data.ICloudPySessionMock.__bases__[0]),
                patch("requests.Session.request", fake_apple),
                # icloudpy consults the keyring for any falsy password. The
                # whole point of session-only mode is that it must not, so
                # make the attempt fatal rather than merely unnecessary.
                patch(
                    "icloudpy.base.get_password_from_keyring",
                    side_effect=AssertionError("the keyring must not be consulted"),
                ),
            ):
                try:
                    api = sync.get_api_instance(
                        username="a@icloud.com",
                        password=None,
                        cookie_directory=cookie_directory,
                    )
                except Exception as error:  # noqa: BLE001 - the test inspects it
                    raised = error
        return api, raised, touched_signin

    def test_end_to_end_a_saved_session_is_enough(self):
        api, raised, touched_signin = self._real_transport_session_only(
            200,
            {"dsInfo": {"hsaVersion": 2}, "webservices": {"drivews": {"status": "active"}}},
        )
        self.assertIsNone(raised)
        self.assertEqual(api.data["webservices"], {"drivews": {"status": "active"}})
        self.assertEqual(touched_signin, [])

    def test_end_to_end_a_real_421_reads_as_a_rejected_session(self):
        """Apple's documented re-auth status. icloudpy keeps it on the
        exception, so it classifies correctly and the user is told to sign
        in again."""
        _, raised, touched_signin = self._real_transport_session_only(
            421,
            {"errorMessage": "Authentication required for Account."},
        )
        self.assertIsInstance(raised, exceptions.ICloudPyNoStoredPasswordAvailableException)
        self.assertIn("no longer valid", str(raised))
        self.assertEqual(touched_signin, [])

    def test_end_to_end_a_json_bodied_401_is_not_classifiable(self):
        """Documents the gap deliberately. For a JSON body outside its own
        re-auth statuses icloudpy discards the HTTP status and reports the
        body's errorCode, so a 401 arrives indistinguishable from an
        outage. It must still never reach Apple's sign-in endpoint, and
        ``_handle_auth_transport_error`` is what stops it going unreported
        (see the loop tests below)."""
        _, raised, touched_signin = self._real_transport_session_only(
            401,
            {"errorMessage": "Unauthorized"},
        )
        self.assertIsInstance(raised, exceptions.ICloudPyAPIResponseException)
        self.assertNotIsInstance(raised, exceptions.ICloudPyNoStoredPasswordAvailableException)
        self.assertIsNone(raised.code)
        self.assertEqual(touched_signin, [])

    def test_end_to_end_a_non_json_401_does_classify(self):
        """The same 401 with an HTML body keeps its status, so it reads as a
        rejected session. Worth pinning: it is the reason the gap above is a
        gap rather than the rule."""
        _, raised, _ = self._real_transport_session_only(
            401,
            {"errorMessage": "Unauthorized"},
            content_type="text/html",
        )
        self.assertIsInstance(raised, exceptions.ICloudPyNoStoredPasswordAvailableException)

    def _transport_error_in_session_only_mode(self, error):
        """Run the transport handler as a session-only cycle would.

        Returns ``(notifier, published)``.
        """
        config = {"app": {"credentials": {"retry_login_interval": 600}}}
        sync_state = sync.SyncState()
        sync_state.session_only = True
        with (
            patch.object(sync, "_auth_retry_sleep"),
            patch.object(sync, "notify") as notifier,
            patch.object(sync, "_publish_auth_blocked") as published,
        ):
            self.assertTrue(
                sync._handle_auth_transport_error(  # noqa: SLF001
                    config,
                    data.AUTHENTICATED_USER,
                    sync_state,
                    error,
                ),
            )
        return notifier, published

    def test_an_unclassifiable_failure_is_never_silent_in_session_only_mode(self):
        """A JSON-bodied 401 arrives with no code, indistinguishable from a
        rejected session, and only a human can revive such a container. So
        this one does earn the "re-auth required" alert -- throttled to one
        message a day -- rather than retrying in silence forever."""
        notifier, published = self._transport_error_in_session_only_mode(
            exceptions.ICloudPyAPIResponseException("Unauthorized"),
        )
        notifier.send.assert_called_once()
        self.assertEqual(published.call_args.kwargs["reason"], "sign_in_failed")
        # The webhook agrees with the alert: a monitor keyed on the reason
        # must not read this as a fault that clears by itself.
        self.assertEqual(
            notifier.send_cycle_event.call_args.kwargs["data"]["reason"],
            "sign_in_failed",
        )

    def test_an_outage_never_asks_a_session_only_container_to_re_authenticate(self):
        """The whole point of classifying: notify.send's text is "iCloud
        re-auth required", and an outage is not that. A 5xx that kept its
        status and a dropped connection are both logged, retried and shown
        on the dashboard -- without waking anyone to re-authenticate over
        Apple having a bad hour."""
        import requests as _requests

        for error in (
            exceptions.ICloudPyAPIResponseException("Service Unavailable", 503),
            exceptions.ICloudPyAPIResponseException("Internal Server Error", 500),
            _requests.exceptions.ConnectionError("name resolution failed"),
            _requests.exceptions.Timeout("timed out"),
        ):
            with self.subTest(error=type(error).__name__):
                notifier, published = self._transport_error_in_session_only_mode(error)
                notifier.send.assert_not_called()
                self.assertEqual(
                    notifier.send_cycle_event.call_args.kwargs["data"]["reason"],
                    "sign_in_error",
                )
                # Still reported as a stoppage: the loop is not syncing, and
                # the dashboard's wording for this reason allows for an
                # outage and asks for nothing.
                self.assertEqual(published.call_args.kwargs["reason"], "sign_in_failed")

    def test_a_rejected_password_still_alerts_in_either_mode(self):
        """ICloudPyFailedLoginException never heals by retrying, so it earns
        the alert whether or not a password is stored."""
        notifier, _ = self._transport_error_in_session_only_mode(
            exceptions.ICloudPyFailedLoginException("rejected"),
        )
        notifier.send.assert_called_once()

    def test_the_password_path_keeps_its_quieter_transport_handling(self):
        """With a password stored, an API error on sign-in is still just
        logged and retried -- notifying on every Apple hiccup would be new
        noise for everyone who is not affected by this change."""
        config = {"app": {"credentials": {"retry_login_interval": 600}}}
        with (
            patch.object(sync, "_auth_retry_sleep"),
            patch.object(sync, "notify") as notifier,
            patch.object(sync, "_publish_auth_blocked") as published,
        ):
            self.assertTrue(
                sync._handle_auth_transport_error(  # noqa: SLF001
                    config,
                    data.AUTHENTICATED_USER,
                    sync.SyncState(),
                    exceptions.ICloudPyAPIResponseException("Service Unavailable", 503),
                ),
            )
        notifier.send.assert_not_called()
        published.assert_not_called()

    def test_the_mode_is_recorded_for_the_error_handlers(self):
        for stored, expected in ((None, True), ("pw", False)):
            with self.subTest(stored=stored):
                sync_state = sync.SyncState()
                retrieve = (
                    {"side_effect": exceptions.ICloudPyNoStoredPasswordAvailableException()}
                    if stored is None
                    else {"return_value": stored}
                )
                with (
                    patch.object(sync, "_retrieve_password", **retrieve),
                    patch.object(sync, "get_api_instance"),
                    patch("src.config_parser.get_region", return_value="global"),
                ):
                    sync._authenticate_and_get_api({}, data.AUTHENTICATED_USER, sync_state)  # noqa: SLF001
                self.assertEqual(sync_state.session_only, expected)
class TestSyncLifecycleWebhooks(unittest.TestCase):
    """Where the pings sit matters more than how they are sent. A success
    ping on a cycle that logged failed downloads would keep a monitor green
    while the library quietly fell behind, and a ping during a dry run would
    report a sync that never happened."""

    CONFIG = {
        "app": {
            "credentials": {"username": "a@icloud.com", "retry_login_interval": 600},
            "webhooks": {
                "start": "https://hc-ping.com/uuid/start",
                "success": "https://hc-ping.com/uuid",
                "failure": "https://hc-ping.com/uuid/fail",
            },
        },
        "drive": {"destination": "drive", "sync_interval": 300},
    }

    def _events_of_one_cycle(self, drive_stats=None, photos_stats=None, dry_run=False):
        """Run a single sync cycle and return the webhook events it fired."""
        api = Mock()
        api.requires_2sa = False
        with (
            patch.object(sync, "_load_configuration", return_value=copy.deepcopy(self.CONFIG)),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(sync, "_authenticate_and_get_api", return_value=api),
            patch.object(sync, "_maybe_refresh_trust"),
            patch.object(sync, "_maybe_warn_trust_expiring"),
            patch.object(sync, "_perform_dry_run"),
            patch.object(sync, "_perform_drive_sync", return_value=drive_stats),
            patch.object(sync, "_perform_photos_sync", return_value=photos_stats),
            patch.object(sync, "_send_usage_statistics"),
            patch.object(sync, "_interruptible_sleep", side_effect=SystemExit),
            patch("src.notify.send_sync_summary"),
            patch("src.notify.send_cycle_event") as cycle,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            if dry_run:
                sync.sync(dry_run=True)
            else:
                with self.assertRaises(SystemExit):
                    sync.sync()
        self.cycle_calls = cycle.call_args_list
        return [call.kwargs["boundary"] for call in self.cycle_calls]

    def test_a_clean_cycle_opens_and_closes(self):
        self.assertEqual(self._events_of_one_cycle(drive_stats=DriveStats()), ["start", "success"])

    def test_failed_downloads_close_the_cycle_as_a_failure(self):
        """On PhotoStats deliberately: DriveStats.errors is never populated
        in production, so a Drive failure cannot reach this boundary today."""
        stats = PhotoStats()
        stats.errors.append("1 photo download(s) failed")
        self.assertEqual(
            self._events_of_one_cycle(drive_stats=DriveStats(), photos_stats=stats),
            ["start", "failure"],
        )
        self.assertEqual(self.cycle_calls[-1].kwargs["data"]["reason"], "download_errors")

    def test_a_clean_cycle_carries_no_reason(self):
        self._events_of_one_cycle(drive_stats=DriveStats())
        self.assertNotIn("reason", self.cycle_calls[-1].kwargs["data"])

    def test_a_dry_run_pings_nothing(self):
        self.assertEqual(self._events_of_one_cycle(dry_run=True), [])

    def _handler_events(self, call_handler):
        with (
            patch.object(sync, "_auth_retry_sleep"),
            patch.object(sync, "_interruptible_sleep"),
            patch("src.notify.send"),
            patch("src.notify.send_cycle_event") as cycle,
        ):
            self.assertTrue(call_handler())
        self.cycle_calls = cycle.call_args_list
        return [call.kwargs["boundary"] for call in self.cycle_calls]

    def test_a_pending_second_factor_is_a_failure(self):
        config = copy.deepcopy(self.CONFIG)
        api = Mock()
        api.security_key_challenge = None
        self.assertEqual(
            self._handler_events(
                lambda: sync._handle_2fa_required(config, "a@icloud.com", sync.SyncState(), api),  # noqa: SLF001
            ),
            ["failure"],
        )

    def test_a_missing_keyring_password_is_a_failure(self):
        config = copy.deepcopy(self.CONFIG)
        self.assertEqual(
            self._handler_events(
                lambda: sync._handle_password_error(  # noqa: SLF001
                    config,
                    "a@icloud.com",
                    sync.SyncState(),
                    exceptions.ICloudPyNoStoredPasswordAvailableException("no session"),
                ),
            ),
            ["failure"],
        )

    def test_a_sign_in_failure_is_a_failure(self):
        config = copy.deepcopy(self.CONFIG)
        error = exceptions.ICloudPyFailedLoginException("401")
        self.assertEqual(
            self._handler_events(
                lambda: sync._handle_auth_transport_error(  # noqa: SLF001
                    config, "a@icloud.com", sync.SyncState(), error,
                ),
            ),
            ["failure"],
        )

    def test_a_failure_after_sign_in_is_a_failure(self):
        config = copy.deepcopy(self.CONFIG)
        self.assertEqual(
            self._handler_events(
                lambda: sync._handle_sync_error(config, Exception("zone unavailable"), 300, 500),  # noqa: SLF001
            ),
            ["failure"],
        )


class TestACycleThatSyncedNothingIsAFailure(unittest.TestCase):
    """A cycle where every due service was skipped carries no errors and no
    counts, so it is indistinguishable from a clean one by its stats. Pinging
    success there is how a monitor stays green while nothing at all is being
    downloaded.

    The trap is the opposite case: with unequal intervals the scheduler
    enables only the service whose timer expired, so one service returning
    nothing is the ordinary cycle, not a fault."""

    CONFIG = {
        "app": {
            "credentials": {"username": "a@icloud.com", "retry_login_interval": 600},
            "webhooks": {"success": "https://hc-ping.com/uuid"},
        },
        "drive": {"destination": "drive", "sync_interval": 300},
        "photos": {"destination": "photos", "sync_interval": 900},
    }

    def _boundary(self, drive_stats, photos_stats, config=None, loops=True, photos_indexing=False):
        def photos(config, api, sync_state, interval):
            # What _wait_for_photos_indexing leaves behind for the cycle.
            sync_state.photos_indexing = photos_indexing
            return photos_stats

        api = Mock()
        api.requires_2sa = False
        with (
            patch.object(sync, "_load_configuration", return_value=copy.deepcopy(config or self.CONFIG)),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(sync, "_authenticate_and_get_api", return_value=api),
            patch.object(sync, "_maybe_refresh_trust"),
            patch.object(sync, "_maybe_warn_trust_expiring"),
            patch.object(sync, "_perform_drive_sync", return_value=drive_stats),
            patch.object(sync, "_perform_photos_sync", side_effect=photos),
            patch.object(sync, "_send_usage_statistics"),
            patch.object(sync, "_interruptible_sleep", side_effect=SystemExit),
            patch("src.notify.send_sync_summary"),
            patch("src.notify.send_cycle_event") as cycle,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            if loops:
                with self.assertRaises(SystemExit):
                    sync.sync()
            else:
                # With nothing configured every interval is negative, so the
                # loop leaves oneshot-style instead of reaching the sleep.
                sync.sync()
        closing = cycle.call_args_list[-1]
        self.cycle_message = closing.kwargs.get("message", "")
        return closing.kwargs["boundary"], closing.kwargs["data"].get("reason")

    def test_a_mount_marker_skipping_every_service_is_a_failure(self):
        self.assertEqual(
            self._boundary(drive_stats=None, photos_stats=None),
            ("failure", "mount_marker_missing"),
        )

    def test_a_photos_cycle_waiting_on_apple_says_so(self):
        """Photos skipped for Apple's indexing, Drive not due: nothing synced,
        but the mount is fine and nobody should go looking at it."""
        self.assertEqual(
            self._boundary(drive_stats=None, photos_stats=None, photos_indexing=True),
            ("failure", "photos_indexing"),
        )
        self.assertIn("indexing", self.cycle_message)

    def test_one_service_not_being_due_is_an_ordinary_success(self):
        """The regression this guards: Photos on a 900s interval is simply
        not due on a Drive cycle, and that must not read as a fault."""
        self.assertEqual(
            self._boundary(drive_stats=DriveStats(), photos_stats=None),
            ("success", None),
        )
        self.assertEqual(
            self._boundary(drive_stats=None, photos_stats=PhotoStats()),
            ("success", None),
        )

    def test_nothing_configured_to_sync_is_a_failure(self):
        config = {
            "app": {
                "credentials": {"username": "a@icloud.com", "retry_login_interval": 600},
                "webhooks": {"success": "https://hc-ping.com/uuid"},
            },
        }
        self.assertEqual(
            self._boundary(drive_stats=None, photos_stats=None, config=config, loops=False),
            ("failure", "nothing_synced"),
        )


class TestSyncWebhookEvents(unittest.TestCase):
    """The POST endpoint sees the whole lifecycle, so each hook point has to
    name its own event rather than reporting a generic failure: a receiver
    that cannot tell "waiting for a code" from "Apple refused the password"
    cannot act on either."""

    CONFIG = {
        "app": {
            "credentials": {"username": "a@icloud.com", "retry_login_interval": 600},
            "webhooks": {"url": "https://receiver.test/hook"},
        },
        "drive": {"destination": "drive", "sync_interval": 300},
    }

    def _alert_event(self, call_handler):
        """Run a retry handler and return the event name it told notify.send."""
        with (
            patch.object(sync, "_auth_retry_sleep"),
            patch.object(sync, "_interruptible_sleep"),
            patch("src.notify.send_cycle_event"),
            patch("src.notify.send") as send_mock,
        ):
            self.assertTrue(call_handler())
        return send_mock.call_args.kwargs["event"]

    def test_a_pending_code_is_distinguishable_from_a_refused_sign_in(self):
        config = copy.deepcopy(self.CONFIG)
        api = Mock()
        api.security_key_challenge = None
        self.assertEqual(
            self._alert_event(
                lambda: sync._handle_2fa_required(config, "a@icloud.com", sync.SyncState(), api),  # noqa: SLF001
            ),
            "two_factor_required",
        )
        self.assertEqual(
            self._alert_event(
                lambda: sync._handle_auth_transport_error(  # noqa: SLF001
                    config,
                    "a@icloud.com",
                    sync.SyncState(),
                    exceptions.ICloudPyFailedLoginException("401"),
                ),
            ),
            "sign_in_failed",
        )
        self.assertEqual(
            self._alert_event(
                lambda: sync._handle_password_error(  # noqa: SLF001
                    config,
                    "a@icloud.com",
                    sync.SyncState(),
                    exceptions.ICloudPyNoStoredPasswordAvailableException("no session"),
                ),
            ),
            "password_missing",
        )

    def test_a_security_key_account_gets_its_own_event(self):
        """Apple sends such an account no code at all, so a receiver that
        prompts for one would be sending the user on a fool's errand."""
        config = copy.deepcopy(self.CONFIG)
        api = Mock()
        api.security_key_challenge = {"challenge": "c", "keyHandles": ["k"]}
        with patch("src.web_signals.record_auth_method"):
            self.assertEqual(
                self._alert_event(
                    lambda: sync._handle_2fa_required(config, "a@icloud.com", sync.SyncState(), api),  # noqa: SLF001
                ),
                "security_key_required",
            )

    def test_a_security_key_cycle_failure_says_security_key(self):
        """The reason has to be computed after detection, or every
        security-key account reports a 2FA prompt that will never arrive."""
        config = copy.deepcopy(self.CONFIG)
        api = Mock()
        api.security_key_challenge = {"challenge": "c", "keyHandles": ["k"]}
        with (
            patch.object(sync, "_auth_retry_sleep"),
            patch("src.web_signals.record_auth_method"),
            patch("src.notify.send"),
            patch("src.notify.send_cycle_event") as cycle,
        ):
            sync._handle_2fa_required(config, "a@icloud.com", sync.SyncState(), api)  # noqa: SLF001
        self.assertEqual(cycle.call_args.kwargs["data"]["reason"], "security_key_required")

    def test_each_cycle_failure_says_why(self):
        config = copy.deepcopy(self.CONFIG)
        reasons = []
        with (
            patch.object(sync, "_auth_retry_sleep"),
            patch.object(sync, "_interruptible_sleep"),
            patch("src.notify.send"),
            patch("src.notify.send_cycle_event") as cycle,
        ):
            api = Mock()
            api.security_key_challenge = None
            sync._handle_2fa_required(config, "a@icloud.com", sync.SyncState(), api)  # noqa: SLF001
            sync._handle_password_error(  # noqa: SLF001
                config,
                "a@icloud.com",
                sync.SyncState(),
                exceptions.ICloudPyNoStoredPasswordAvailableException("no session"),
            )
            sync._handle_auth_transport_error(  # noqa: SLF001
                config,
                "a@icloud.com",
                sync.SyncState(),
                exceptions.ICloudPyFailedLoginException("401"),
            )
            # Offline at boot: the attempt never completed; nothing was refused.
            sync._handle_auth_transport_error(  # noqa: SLF001
                config,
                "a@icloud.com",
                sync.SyncState(),
                requests.exceptions.ConnectionError("offline"),
            )
            sync._handle_sync_error(config, Exception("zone"), 300, 500)  # noqa: SLF001
            reasons = [call.kwargs["data"]["reason"] for call in cycle.call_args_list]
        self.assertEqual(
            reasons,
            ["two_factor_required", "password_missing", "sign_in_failed", "sign_in_error", "sync_error"],
        )

    def test_a_successful_refresh_reports_the_new_expiry(self):
        """Nothing else notifies on a refresh, so the webhook is the only way
        a receiver tracking the trust window learns it moved."""
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        api = Mock()
        api.trust_session.return_value = True
        with (
            patch.object(
                sync,
                "_read_trust_cookie_expiry",
                side_effect=[
                    now + datetime.timedelta(days=3, minutes=1),
                    now + datetime.timedelta(days=90),
                ],
            ),
            patch("src.notify.post_event_to_webhook") as post_mock,
        ):
            sync._maybe_refresh_trust({}, api)  # noqa: SLF001
        event, message, data = post_mock.call_args.args[1:]
        self.assertEqual(event, "trust_refreshed")
        self.assertIn("refreshed", message)
        self.assertEqual(data["days_remaining_before"], 3)
        self.assertEqual(data["expires_at"], (now + datetime.timedelta(days=90)).isoformat())

    def test_an_unreadable_expiry_is_omitted_rather_than_nulled(self):
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        api = Mock()
        api.trust_session.return_value = True
        with (
            patch.object(
                sync,
                "_read_trust_cookie_expiry",
                side_effect=[now + datetime.timedelta(days=3, minutes=1), None],
            ),
            patch("src.notify.post_event_to_webhook") as post_mock,
        ):
            sync._maybe_refresh_trust({}, api)  # noqa: SLF001
        self.assertEqual(post_mock.call_args.args[3], {"days_remaining_before": 3})

    def test_a_declined_refresh_reports_nothing(self):
        api = Mock()
        api.trust_session.return_value = False
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        with (
            patch.object(sync, "_read_trust_cookie_expiry", return_value=now + datetime.timedelta(days=3)),
            patch("src.notify.post_event_to_webhook") as post_mock,
        ):
            sync._maybe_refresh_trust({}, api)  # noqa: SLF001
        post_mock.assert_not_called()

    def test_the_cycle_end_event_carries_the_stats(self):
        """A webhook-only install never enables app.notifications, so the
        cycle event is where its statistics have to live."""
        api = Mock()
        api.requires_2sa = False
        stats = DriveStats(files_downloaded=4)
        with (
            patch.object(sync, "_load_configuration", return_value=copy.deepcopy(self.CONFIG)),
            patch.object(sync, "alive"),
            patch.object(sync, "_log_sync_intervals_at_startup"),
            patch.object(sync, "_authenticate_and_get_api", return_value=api),
            patch.object(sync, "_maybe_refresh_trust"),
            patch.object(sync, "_maybe_warn_trust_expiring"),
            patch.object(sync, "_perform_drive_sync", return_value=stats),
            patch.object(sync, "_perform_photos_sync", return_value=None),
            patch.object(sync, "_send_usage_statistics"),
            patch.object(sync, "_interruptible_sleep", side_effect=SystemExit),
            patch("src.notify.requests.get"),
            patch("src.notify.requests.post") as post_mock,
            patch("src.config_parser.get_username", return_value="a@icloud.com"),
        ):
            post_mock.return_value = Mock(ok=True)
            with self.assertRaises(SystemExit):
                sync.sync()
        posted = [call.kwargs["json"] for call in post_mock.call_args_list]
        self.assertEqual([p["event"] for p in posted], ["sync_started", "sync_succeeded"])
        self.assertEqual(posted[1]["data"]["drive"]["files_downloaded"], 4)
        self.assertFalse(posted[1]["data"]["has_errors"])
