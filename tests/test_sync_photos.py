__author__ = "Mandar Patil (mandarons@pm.me)"

import unittest
import os

from io import StringIO
import shutil
from unittest.mock import patch

import pyicloud

import tests
from tests import data
from src import sync_photos, config_parser


class TestSync(unittest.TestCase):
    def setUp(self) -> None:
        self.config = config_parser.read_config(config_path=tests.CONFIG_PATH)
        self.filters = self.config["drive"]["filters"]
        self.root = tests.DRIVE_DIR
        self.destination_path = self.root
        os.makedirs(self.destination_path, exist_ok=True)
        self.service = data.PyiCloudServiceMock(
            data.AUTHENTICATED_USER, data.VALID_PASSWORD
        )
        self.drive = self.service.drive
        self.items = self.drive.dir()
        self.file_item = self.drive[self.items[4]]["Test"]["Scanned document 1.pdf"]
        self.file_name = "Scanned document 1.pdf"
        self.local_file_path = os.path.join(self.destination_path, self.file_name)

    def tearDown(self) -> None:
        shutil.rmtree(tests.TEMP_DIR)

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("pyicloud.PyiCloudService")
    @patch("src.config_parser.read_config")
    def test_sync_drive_valids(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
        mock_sleep,
    ):
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        mock_read_config.return_value = config
        self.assertIsNone(sync_photos.sync_photos())
        self.assertTrue(
            os.path.isdir(
                os.path.join(
                    self.destination_path, config["photos"]["filters"]["albums"][0]
                )
            )
        )
        self.assertTrue(
            os.path.isdir(
                os.path.join(
                    self.destination_path, config["photos"]["filters"]["albums"][1]
                )
            )
        )
        shutil.copyfile(
            os.path.join(os.path.dirname(__file__), "data", "thumb.jpeg"),
            os.path.join(
                self.destination_path,
                config["photos"]["filters"]["albums"][1],
                "IMG_3148__original.JPG",
            ),
        )
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            self.assertIsNone(sync_photos.sync_photos())
            output = mock_stdout.getvalue()
            self.assertIn("Downloading", output)
        self.assertTrue(
            os.path.isdir(
                os.path.join(
                    self.destination_path, config["photos"]["filters"]["albums"][0]
                )
            )
        )
        self.assertTrue(
            os.path.isdir(
                os.path.join(
                    self.destination_path, config["photos"]["filters"]["albums"][1]
                )
            )
        )

        mock_get_username.return_value = data.REQUIRES_2FA_USER
        self.assertIsNone(sync_photos.sync_photos())

        mock_get_password.return_value = None
        self.assertIsNone(sync_photos.sync_photos())

        mock_sleep.side_effect = Exception()
        config["app"]["sync_interval"] = 1
        with self.assertRaises(Exception):
            sync_photos.sync_photos()

    def test_download_photo_invalids(self):
        class MockPhoto:
            def download(self, quality):
                raise pyicloud.exceptions.PyiCloudAPIResponseException

        self.assertFalse(
            sync_photos.download_photo(None, ["original"], self.destination_path)
        )
        self.assertFalse(
            sync_photos.download_photo(MockPhoto(), None, self.destination_path)
        )
        self.assertFalse(sync_photos.download_photo(MockPhoto(), ["original"], None))
        self.assertFalse(
            sync_photos.download_photo(MockPhoto(), ["original"], self.destination_path)
        )

    def test_sync_album_invalids(self):
        self.assertIsNone(
            sync_photos.sync_album(None, self.destination_path, ["original"])
        )
        self.assertIsNone(sync_photos.sync_album({}, None, ["original"]))
        self.assertIsNone(sync_photos.sync_album({}, self.destination_path, None))
