"""Tests for sync_photos.py file."""
__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import shutil
import unittest
from unittest.mock import patch

import icloudpy

import tests
from src import LOGGER, read_config, sync_photos
from tests import DATA_DIR, data


class TestSyncPhotos(unittest.TestCase):
    """Tests for sync_photos file."""

    def setUp(self) -> None:
        """Initialize tests."""
        self.config = read_config(config_path=tests.CONFIG_PATH)

        self.root = tests.PHOTOS_DIR

        self.destination_path = self.root
        os.makedirs(self.destination_path, exist_ok=True)
        self.service = data.ICloudPyServiceMock(
            data.AUTHENTICATED_USER, data.VALID_PASSWORD
        )

    def tearDown(self) -> None:
        """Remove temp directory."""
        shutil.rmtree(tests.TEMP_DIR)
        if os.path.exists(tests.PHOTOS_DIR):
            shutil.rmtree(tests.PHOTOS_DIR)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_original(
        self, mock_read_config, mock_service, mock_get_username, mock_get_password
    ):
        """Test for successful original photo size download."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        mock_read_config.return_value = config
        # Sync original photos
        self.assertIsNone(
            sync_photos.sync_photos(config=config, photos=mock_service.photos)
        )
        album_2_path = os.path.join(self.destination_path, "album 2")
        album_1_1_path = os.path.join(album_2_path, "album-1-1")
        album_1_path = os.path.join(self.destination_path, "album-1")
        self.assertTrue(os.path.isdir(album_2_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(os.path.isdir(album_1_1_path))
        self.assertTrue(len(os.listdir(album_2_path)) > 1)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_all_albums_filtered(
        self, mock_read_config, mock_service, mock_get_username, mock_get_password
    ):
        """Test for successful original photo size download."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["all_albums"] = True
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
        self.assertFalse(os.path.isdir(album_0_path))
        self.assertFalse(os.path.isdir(album_1_path))

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_all_albums_not_filtered(
        self, mock_read_config, mock_service, mock_get_username, mock_get_password
    ):
        """Test for successful original photo size download."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["all_albums"] = True
        mock_read_config.return_value = config
        album_0_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][0]
        )
        album_1_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][1]
        )
        config["photos"]["filters"]["albums"] = None
        # Sync original photos
        self.assertIsNone(
            sync_photos.sync_photos(config=config, photos=mock_service.photos)
        )
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 1)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

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
    ):
        """Test if missing local file is downloaded successfully."""
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

        os.remove(
            os.path.join(
                album_1_path,
                "IMG_3148__medium__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG",
            )
        )
        # Download missing file
        with self.assertLogs() as captured:
            self.assertIsNone(
                sync_photos.sync_photos(config=config, photos=mock_service.photos)
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNotNone(
                next(
                    (
                        s
                        for s in captured[1]
                        if "album-1/IMG_3148__medium__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG ..."
                        in s
                    ),
                    None,
                )
            )
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 0)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

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
    ):
        """Test if changed photo downloads successfully."""
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
        os.remove(
            os.path.join(
                album_1_path,
                "IMG_3148__medium__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG",
            )
        )
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
                next(
                    (
                        s
                        for s in captured[1]
                        if "album-1/IMG_3148__medium__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG ..."
                        in s
                    ),
                    None,
                )
            )
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 0)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

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
    ):
        """Test if there is nothing new to download."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        mock_read_config.return_value = config

        sync_photos.sync_photos(config=config, photos=mock_service.photos)

        # No files to download
        with self.assertLogs(logger=LOGGER, level="DEBUG") as captured:
            self.assertIsNone(
                sync_photos.sync_photos(config=config, photos=mock_service.photos)
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNone(
                next((s for s in captured[1] if "Downloading /" in s), None)
            )

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
    ):
        """Test for renaming of previously downloaded original photos."""
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
            os.path.join(
                album_1_path,
                "IMG_3148__original__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG",
            ),
            os.path.join(album_1_path, "IMG_3148.JPG"),
        )

        with self.assertLogs(logger=LOGGER, level="DEBUG") as captured:
            self.assertIsNone(
                sync_photos.sync_photos(config=config, photos=mock_service.photos)
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNone(
                next((s for s in captured[1] if "Downloading /" in s), None)
            )

        self.assertFalse(os.path.exists(os.path.join(album_1_path, "IMG_3148.JPG")))

        # Rename previous __original files - upgrade to newer version
        os.rename(
            os.path.join(
                album_1_path,
                "IMG_3148__original__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG",
            ),
            os.path.join(album_1_path, "IMG_3148__original.JPG"),
        )

        with self.assertLogs(logger=LOGGER, level="DEBUG") as captured:
            self.assertIsNone(
                sync_photos.sync_photos(config=config, photos=mock_service.photos)
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNone(
                next((s for s in captured[1] if "Downloading /" in s), None)
            )

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_rename_original_photos_obsolete_false(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        """Test for renaming of previously downloaded original photos."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["remove_obsolete"] = False
        mock_read_config.return_value = config
        album_1_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][1]
        )
        sync_photos.sync_photos(config=config, photos=mock_service.photos)

        # Rename previous original files - upgrade to newer version
        os.rename(
            os.path.join(
                album_1_path,
                "IMG_3148__original__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG",
            ),
            os.path.join(album_1_path, "delete_me.JPG"),
        )

        sync_photos.sync_photos(config=config, photos=mock_service.photos)

        self.assertTrue(os.path.exists(os.path.join(album_1_path, "delete_me.JPG")))

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_rename_original_photos_obsolete_true(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        """Test for renaming of previously downloaded original photos."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["remove_obsolete"] = True
        mock_read_config.return_value = config
        album_1_path = os.path.join(
            self.destination_path, config["photos"]["filters"]["albums"][1]
        )
        sync_photos.sync_photos(config=config, photos=mock_service.photos)

        # Rename previous original files - upgrade to newer version
        os.rename(
            os.path.join(
                album_1_path,
                "IMG_3148__original__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG",
            ),
            os.path.join(album_1_path, "delete_me.JPG"),
        )

        sync_photos.sync_photos(config=config, photos=mock_service.photos)

        self.assertFalse(os.path.exists(os.path.join(album_1_path, "delete_me.JPG")))

    def test_remove_obsolete_none_destination_path(self):
        """Test for destination path as None."""
        self.assertTrue(
            len(sync_photos.remove_obsolete(destination_path=None, files=set())) == 0
        )

    def test_remove_obsolete_none_files(self):
        """Test for files as None."""
        obsolete_path = os.path.join(self.destination_path, "obsolete")
        self.assertTrue(
            len(sync_photos.remove_obsolete(destination_path=obsolete_path, files=None))
            == 0
        )

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
    ):
        """Test for empty albums list."""
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
                next(
                    (
                        s
                        for s in captured[1]
                        if "all/IMG_3148__original__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG ..."
                        in s
                    ),
                    None,
                )
            )

        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "all")))

    def test_download_photo_none_photo(self):
        """Test if download_photo has photo as None."""
        self.assertFalse(
            sync_photos.download_photo(None, ["original"], self.destination_path)
        )

    def test_download_photo_none_file_size(self):
        """Test if download_photo has file size as None."""

        class MockPhoto:
            def download(self, quality):
                raise icloudpy.exceptions.ICloudPyAPIResponseException

        self.assertFalse(
            sync_photos.download_photo(MockPhoto(), None, self.destination_path)
        )

    def test_download_photo_none_destination_path(self):
        """Test if download_photo has destination path as None."""

        class MockPhoto:
            def download(self, quality):
                raise icloudpy.exceptions.ICloudPyAPIResponseException

        self.assertFalse(sync_photos.download_photo(MockPhoto(), ["original"], None))

    def test_download_photo_handle_exception(self):
        """Test if exception is thrown in dowonload_photo."""

        class MockPhoto:
            def download(self, quality):
                raise icloudpy.exceptions.ICloudPyAPIResponseException

        self.assertFalse(
            sync_photos.download_photo(MockPhoto(), ["original"], self.destination_path)
        )

    def test_sync_album_none_album(self):
        """Test if album is None."""
        self.assertIsNone(
            sync_photos.sync_album(None, self.destination_path, ["original"])
        )

    def test_sync_album_none_destination_path(self):
        """Test if destination path is None."""
        self.assertIsNone(sync_photos.sync_album({}, None, ["original"]))

    def test_sync_album_none_file_sizes(self):
        """Test if file size is None."""
        self.assertIsNone(sync_photos.sync_album({}, self.destination_path, None))

    def test_missing_medium_photo_size(self):
        """Test if medium photo size is missing."""

        class MockPhoto:
            @property
            def id(self):
                return "some-random-id"

            @property
            def filename(self):
                return "filename.JPG"

            @property
            def versions(self):
                return {"original": "exists"}

        self.assertFalse(
            sync_photos.process_photo(
                photo=MockPhoto(),
                file_size="medium",
                destination_path=self.destination_path,
                files=None,
            )
        )

    def test_missing_thumb_photo_sizes(self):
        """Test if thumbnail size is missing."""

        class MockPhoto:
            @property
            def id(self):
                return "some-random-id"

            @property
            def filename(self):
                return "filename.JPG"

            @property
            def versions(self):
                return {"original": "exists"}

        self.assertFalse(
            sync_photos.process_photo(
                photo=MockPhoto(),
                file_size="thumb",
                destination_path=self.destination_path,
                files=None,
            )
        )

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_photo_wanted_extensions_jpg(
        self, mock_read_config, mock_service, mock_get_username, mock_get_password
    ):
        """Test for JPG extension filter."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["filters"]["extensions"] = ["JpG"]
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
        self.assertTrue(len(os.listdir(album_0_path)) > 1)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_photo_wanted_extensions_png(
        self, mock_read_config, mock_service, mock_get_username, mock_get_password
    ):
        """Test for PNG extension filter."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["filters"]["extensions"] = ["PnG"]
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
        self.assertTrue(len(os.listdir(album_0_path)) == 1)
        self.assertTrue(len(os.listdir(album_1_path)) == 0)
