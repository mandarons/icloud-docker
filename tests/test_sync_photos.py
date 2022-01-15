__author__ = "Mandar Patil (mandarons@pm.me)"

import unittest
import os
from io import StringIO
import shutil
from unittest.mock import patch
import pyicloud
import tests
from tests import DATA_DIR, data
from src import sync_photos, config_parser


class TestSyncPhotos(unittest.TestCase):
    def setUp(self) -> None:
        self.config = config_parser.read_config(config_path=tests.CONFIG_PATH)

        self.root = tests.PHOTOS_DIR

        self.destination_path = self.root
        os.makedirs(self.destination_path, exist_ok=True)
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
    def test_sync_photos_valids(
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
        # Sync original photos
        self.assertIsNone(
            sync_photos.sync_photos(
                config=config, photos=mock_service.photos, verbose=True
            )
        )
        album_0_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][0]
        )
        album_1_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][1]
        )
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 0)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

        # Download missing file
        os.remove(os.path.join(album_1_path, "IMG_3148.JPG"))
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            self.assertIsNone(
                sync_photos.sync_photos(
                    config=config, photos=mock_service.photos, verbose=True
                )
            )
            output = mock_stdout.getvalue()
            self.assertIn("album-1/IMG_3148.JPG ...", output)
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 0)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

        # Download changed file
        os.remove(os.path.join(album_1_path, "IMG_3148.JPG"))
        shutil.copyfile(
            os.path.join(DATA_DIR, "thumb.jpeg"),
            os.path.join(album_1_path, "IMG_3148.JPG"),
        )
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            self.assertIsNone(
                sync_photos.sync_photos(
                    config=config, photos=mock_service.photos, verbose=True
                )
            )
            output = mock_stdout.getvalue()
            self.assertIn("album-1/IMG_3148.JPG ...", output)
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 0)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

        # No files to download
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            self.assertIsNone(
                sync_photos.sync_photos(
                    config=config, photos=mock_service.photos, verbose=True
                )
            )
            output = mock_stdout.getvalue()
            self.assertNotIn("Downloading /", output)

        # Rename previous original files - upgrade to newer version
        os.rename(
            os.path.join(album_1_path, "IMG_3148.JPG"),
            os.path.join(album_1_path, "IMG_3148__original.JPG"),
        )

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            self.assertIsNone(
                sync_photos.sync_photos(
                    config=config, photos=mock_service.photos, verbose=True
                )
            )
            output = mock_stdout.getvalue()
            self.assertNotIn("Downloading /", output)

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("pyicloud.PyiCloudService")
    @patch("src.config_parser.read_config")
    def test_sync_photos_valid_empty_albums_list(
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
        config["photos"]["filters"]["albums"] = []
        mock_read_config.return_value = config
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            self.assertIsNone(
                sync_photos.sync_photos(
                    config=config, photos=mock_service.photos, verbose=True
                )
            )
            output = mock_stdout.getvalue()
            self.assertIn("all/IMG_3148.JPG ...", output)

        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "all")))

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
