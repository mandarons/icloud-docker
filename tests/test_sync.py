"""Tests for sync.py file."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import shutil
import unittest
from copy import deepcopy
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from icloudpy import exceptions

import tests
from src import ENV_ICLOUD_PASSWORD_KEY, config_parser, read_config, sync
from src.sync_stats import DriveStats
from tests import data


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
        self.assertTrue(os.path.isdir("/config/session_data"))

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
        dir_length = len(os.listdir(self.root_dir))
        self.assertTrue(dir_length == 1)
        self.assertTrue(os.path.isdir(os.path.join(self.root_dir, config["photos"]["destination"])))

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
        dir_length = len(os.listdir(self.root_dir))
        self.assertTrue(dir_length == 1)

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

    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_sync_password_missing_in_keyring(
        self,
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
                        if "Password is not stored in keyring. Please save the password in keyring." in e
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
        self.assertEqual(mock_sync_drive.sync_drive.call_count, 6)
        self.assertEqual(mock_sync_photos.sync_photos.call_count, 3)

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
    def test_sync_negative_retry_login_interval_without_keyring_password(
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
        self.assertTrue(len([e for e in captured[1] if "Password is not stored in keyring." in e]) > 0)
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
        # Verify sleep was called (indicating the loop continued)
        mock_sleep.assert_called_once()

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
