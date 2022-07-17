__author__ = "Mandar Patil (mandarons@pm.me)"

from io import StringIO
import unittest
import os

import shutil
from unittest.mock import patch

import tests
from tests import data
from src import ENV_ICLOUD_PASSWORD_KEY, sync, read_config


class TestSyncDrive(unittest.TestCase):
    def remove_temp(self):
        if os.path.exists(tests.TEMP_DIR):
            shutil.rmtree(tests.TEMP_DIR)
        if os.path.exists("session_data"):
            shutil.rmtree("session_data")
        if os.path.exists("icloud"):
            shutil.rmtree("icloud")

    def setUp(self) -> None:
        self.config = read_config(config_path=tests.CONFIG_PATH)
        self.root_dir = tests.TEMP_DIR
        self.config["app"]["root"] = self.root_dir
        os.makedirs(tests.TEMP_DIR, exist_ok=True)
        self.service = data.ICloudPyServiceMock(
            data.AUTHENTICATED_USER, data.VALID_PASSWORD
        )

    def tearDown(self) -> None:
        self.remove_temp()

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    def test_sync(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        mock_service = self.service
        config = self.config.copy()
        mock_read_config.return_value = config
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]
        self.assertIsNone(sync.sync())
        self.assertTrue(os.path.isdir("./session_data"))

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    def test_sync_photos_only(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        mock_service = self.service
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]
        # Sync only photos
        config = self.config.copy()
        del config["drive"]
        self.remove_temp()
        mock_read_config.return_value = config
        self.assertIsNone(sync.sync())
        dir_length = len(os.listdir(self.root_dir))
        self.assertTrue(1 == dir_length)
        self.assertTrue(
            os.path.isdir(os.path.join(self.root_dir, config["photos"]["destination"]))
        )

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    def test_sync_drive_only(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        mock_service = self.service
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        # Sync only drive
        config = self.config.copy()
        del config["photos"]
        self.remove_temp()
        mock_read_config.return_value = config
        self.assertIsNone(sync.sync())
        self.assertTrue(
            os.path.isdir(os.path.join(self.root_dir, config["drive"]["destination"]))
        )
        dir_length = len(os.listdir(self.root_dir))
        self.assertTrue(1 == dir_length)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    def test_sync_empty(
        self, mock_read_config, mock_service, mock_get_username, mock_get_password
    ):
        mock_service = self.service
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        # Nothing to sync
        config = self.config.copy()
        del config["photos"]
        del config["drive"]
        self.remove_temp()
        mock_read_config.return_value = config
        self.assertIsNone(sync.sync())
        self.assertFalse(os.path.exists(self.root_dir))

    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    def test_sync_2fa_required(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        mock_service = self.service
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
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    def test_sync_password_missing_in_keyring(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        mock_service = self.service
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
                        if "Password is not stored in keyring. Please save the password in keyring."
                        in e
                    ]
                )
                > 0
            )

    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value="keyring_password")
    @patch(target="src.config_parser.get_username", return_value=data.REQUIRES_2FA_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    def test_sync_password_as_environment_variable(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        mock_service = self.service
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
                self.assertTrue(
                    len(
                        [
                            e
                            for e in captured[1]
                            if "Error: 2FA is required. Please log in." in e
                        ]
                    )
                    > 0
                )

    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    def test_sync_exception_thrown(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        mock_service = self.service
        config = self.config.copy()
        config["drive"]["sync_interval"] = 1
        config["drive"]["sync_interval"] = 1
        mock_read_config.return_value = config
        mock_sleep.side_effect = Exception()
        config = self.config.copy()
        mock_read_config.return_value = config
        with self.assertRaises(Exception):
            sync.sync()

    # Test different schedule for drive and photos
    @patch("src.sync.sync_drive")
    @patch("src.sync.sync_photos")
    @patch(target="sys.stdout", new_callable=StringIO)
    @patch("src.sync.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.sync.read_config")
    def test_sync_different_schedule(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
        mock_stdout,
        mock_sync_photos,
        mock_sync_drive,
    ):
        mock_service = self.service
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

    @patch("src.sync.read_config")
    def test_get_api_instance_default(
        self,
        mock_read_config,
    ):
        config = self.config.copy()
        config["app"]["region"] = "invalid"
        mock_read_config.return_value = config
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        actual = sync.get_api_instance(
            username=data.AUTHENTICATED_USER, password=data.VALID_PASSWORD
        )
        self.assertNotIn(".com.cn", actual.home_endpoint)
        self.assertNotIn(".com.cn", actual.setup_endpoint)

    @patch("src.sync.read_config")
    def test_get_api_instance_china_region(
        self,
        mock_read_config,
    ):
        config = self.config.copy()
        config["app"]["region"] = "china"
        mock_read_config.return_value = config
        if ENV_ICLOUD_PASSWORD_KEY in os.environ:
            del os.environ[ENV_ICLOUD_PASSWORD_KEY]

        actual = sync.get_api_instance(
            username=data.AUTHENTICATED_USER, password=data.VALID_PASSWORD
        )
        self.assertNotIn(".com.cn", actual.home_endpoint)
        self.assertNotIn(".com.cn", actual.setup_endpoint)
