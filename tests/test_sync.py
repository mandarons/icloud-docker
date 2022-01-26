__author__ = "Mandar Patil (mandarons@pm.me)"

import unittest
import os

import shutil
from unittest.mock import patch

import tests
from tests import data
from src import config_parser, sync


class TestSyncDrive(unittest.TestCase):
    def remove_temp(self):
        if os.path.exists(tests.TEMP_DIR):
            shutil.rmtree(tests.TEMP_DIR)

    def setUp(self) -> None:
        self.config = config_parser.read_config(config_path=tests.CONFIG_PATH)
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
    @patch("src.config_parser.read_config")
    def test_sync_valids(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        mock_service = self.service
        config = self.config.copy()
        mock_read_config.return_value = config

        self.assertIsNone(sync.sync())

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.config_parser.read_config")
    def test_sync_photos_only(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        mock_service = self.service
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

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.config_parser.read_config")
    def test_sync_drive_only(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        mock_service = self.service
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
    @patch("src.config_parser.read_config")
    def test_sync_empty(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        # mock_sleep,
    ):
        mock_service = self.service

        # Nothing to sync
        config = self.config.copy()
        del config["photos"]
        del config["drive"]
        self.remove_temp()
        mock_read_config.return_value = config
        self.assertIsNone(sync.sync())
        self.assertFalse(os.path.exists(self.root_dir))

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.config_parser.read_config")
    def test_sync_invalids(
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

        mock_get_username.return_value = data.REQUIRES_2FA_USER
        self.assertIsNone(sync.sync())

        mock_get_password.return_value = None
        self.assertIsNone(sync.sync())

        mock_sleep.side_effect = Exception()
        config = self.config.copy()
        config["app"]["sync_interval"] = 1
        mock_read_config.return_value = config
        with self.assertRaises(Exception):
            sync.sync()
