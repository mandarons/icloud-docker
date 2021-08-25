__author__ = "Mandar Patil (mandarons@pm.me)"

import unittest
import os

# from io import StringIO
import shutil
from unittest.mock import patch

import tests
from tests import data
from src import config_parser, sync


class TestSyncDrive(unittest.TestCase):
    def setUp(self) -> None:
        self.config = config_parser.read_config(config_path=tests.CONFIG_PATH)
        os.makedirs(tests.TEMP_DIR, exist_ok=True)
        self.service = data.PyiCloudServiceMock(
            data.AUTHENTICATED_USER, data.VALID_PASSWORD
        )

    def tearDown(self) -> None:
        shutil.rmtree(tests.TEMP_DIR)

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("pyicloud.PyiCloudService")
    @patch("src.config_parser.read_config")
    @patch(target="src.sync_photos.sync_photos", return_value=[])
    @patch(target="src.sync_drive.sync_drive", return_value=[])
    def test_sync_valids(
        self,
        mock_sync_drive,
        mock_sync_photos,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        mock_service = self.service
        config = self.config.copy()
        mock_read_config.return_value = config
        self.assertIsNone(sync.sync())

        mock_get_username.return_value = data.REQUIRES_2FA_USER
        self.assertIsNone(sync.sync())

        mock_get_password.return_value = None
        self.assertIsNone(sync.sync())

        mock_sleep.side_effect = Exception()
        config["app"]["sync_interval"] = 1
        with self.assertRaises(Exception):
            sync.sync()
