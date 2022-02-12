__author__ = "Mandar Patil (mandarons@pm.me)"

import unittest
import os
import shutil
from unittest.mock import patch
import icloudpy
import tests
from tests import DATA_DIR, data
from src import sync_photos, read_config


class TestSyncPhotos(unittest.TestCase):
    def setUp(self) -> None:
        self.config = read_config(config_path=tests.CONFIG_PATH)

        self.root = tests.PHOTOS_DIR

        self.destination_path = self.root
        os.makedirs(self.destination_path, exist_ok=True)
        self.service = data.ICloudPyServiceMock(
            data.AUTHENTICATED_USER, data.VALID_PASSWORD
        )

    def tearDown(self) -> None:
        shutil.rmtree(tests.TEMP_DIR)

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_original(
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
            sync_photos.sync_photos(config=config, photos=mock_service.photos)
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

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_missing_photo_download(
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
        album_0_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][0]
        )
        album_1_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][1]
        )
        sync_photos.sync_photos(config=config, photos=mock_service.photos)

        os.remove(os.path.join(album_1_path, "IMG_3148.JPG"))
        # Download missing file
        with self.assertLogs() as captured:
            self.assertIsNone(
                sync_photos.sync_photos(config=config, photos=mock_service.photos)
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNotNone(
                next((s for s in captured[1] if "album-1/IMG_3148.JPG ..." in s), None)
            )
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 0)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_download_changed_photo(
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
        album_0_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][0]
        )
        album_1_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][1]
        )
        sync_photos.sync_photos(config=config, photos=mock_service.photos)
        # Download changed file
        os.remove(os.path.join(album_1_path, "IMG_3148.JPG"))
        shutil.copyfile(
            os.path.join(DATA_DIR, "thumb.jpeg"),
            os.path.join(album_1_path, "IMG_3148.JPG"),
        )
        with self.assertLogs() as captured:
            self.assertIsNone(
                sync_photos.sync_photos(config=config, photos=mock_service.photos)
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNotNone(
                next((s for s in captured[1] if "album-1/IMG_3148.JPG ..." in s), None)
            )
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 0)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_nothing_to_download(
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

        sync_photos.sync_photos(config=config, photos=mock_service.photos)

        # No files to download
        with self.assertLogs() as captured:
            self.assertIsNone(
                sync_photos.sync_photos(config=config, photos=mock_service.photos)
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNone(
                next((s for s in captured[1] if "Downloading /" in s), None)
            )

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_rename_previous_original_photos(
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
        album_1_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][1]
        )
        sync_photos.sync_photos(config=config, photos=mock_service.photos)

        # Rename previous original files - upgrade to newer version
        os.rename(
            os.path.join(album_1_path, "IMG_3148.JPG"),
            os.path.join(album_1_path, "IMG_3148__original.JPG"),
        )

        with self.assertLogs() as captured:
            self.assertIsNone(
                sync_photos.sync_photos(config=config, photos=mock_service.photos)
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNone(
                next((s for s in captured[1] if "Downloading /" in s), None)
            )

    @patch("time.sleep")
    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_empty_albums_list(
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
        with self.assertLogs() as captured:
            self.assertIsNone(
                sync_photos.sync_photos(config=config, photos=mock_service.photos)
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNotNone(
                next((s for s in captured[1] if "all/IMG_3148.JPG ..." in s), None)
            )

        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "all")))

    def test_download_photo_none_photo(self):

        self.assertFalse(
            sync_photos.download_photo(None, ["original"], self.destination_path)
        )

    def test_download_photo_none_file_size(self):
        class MockPhoto:
            def download(self, quality):
                raise icloudpy.exceptions.ICloudPyAPIResponseException

        self.assertFalse(
            sync_photos.download_photo(MockPhoto(), None, self.destination_path)
        )

    def test_download_photo_none_destination_path(self):
        class MockPhoto:
            def download(self, quality):
                raise icloudpy.exceptions.ICloudPyAPIResponseException

        self.assertFalse(sync_photos.download_photo(MockPhoto(), ["original"], None))

    def test_download_photo_handle_exception(self):
        class MockPhoto:
            def download(self, quality):
                raise icloudpy.exceptions.ICloudPyAPIResponseException

        self.assertFalse(
            sync_photos.download_photo(MockPhoto(), ["original"], self.destination_path)
        )

    def test_sync_album_none_album(self):
        self.assertIsNone(
            sync_photos.sync_album(None, self.destination_path, ["original"])
        )

    def test_sync_album_none_destination_path(self):
        self.assertIsNone(sync_photos.sync_album({}, None, ["original"]))

    def test_sync_album_none_file_sizes(self):
        self.assertIsNone(sync_photos.sync_album({}, self.destination_path, None))

    def test_missing_medium_photo_size(self):
        class MockPhoto:
            @property
            def filename(self):
                return "filename"

            @property
            def versions(self):
                return {"original": "exists"}

        self.assertFalse(
            sync_photos.process_photo(
                photo=MockPhoto(),
                file_size="medium",
                destination_path=self.destination_path,
            )
        )

    def test_missing_thumb_photo_sizes(self):
        class MockPhoto:
            @property
            def filename(self):
                return "filename"

            @property
            def versions(self):
                return {"original": "exists"}

        self.assertFalse(
            sync_photos.process_photo(
                photo=MockPhoto(),
                file_size="thumb",
                destination_path=self.destination_path,
            )
        )
