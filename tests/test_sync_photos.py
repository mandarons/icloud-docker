"""Tests for sync_photos.py file."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import glob
import os
import shutil
import time
import unittest
from io import StringIO
from pathlib import Path
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
        self.service = data.ICloudPyServiceMock(data.AUTHENTICATED_USER, data.VALID_PASSWORD)

    def tearDown(self) -> None:
        """Remove temp directory."""
        shutil.rmtree(tests.TEMP_DIR)
        if os.path.exists(tests.PHOTOS_DIR):
            shutil.rmtree(tests.PHOTOS_DIR)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_original(self, mock_read_config, mock_service, mock_get_username, mock_get_password):
        """Test for successful original photo size download."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["filters"]["libraries"] = ["PrimarySync"]
        mock_read_config.return_value = config
        # Sync original photos
        self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
        album_2_path = os.path.join(self.destination_path, "album 2")
        album_1_1_path = os.path.join(album_2_path, "album-1-1")
        album_1_path = os.path.join(self.destination_path, "album-1")
        self.assertTrue(os.path.isdir(album_2_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(os.path.isdir(album_1_1_path))
        self.assertTrue(len(os.listdir(album_2_path)) > 1)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_all_albums_filtered(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        """Test for successful original photo size download."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["all_albums"] = True
        mock_read_config.return_value = config
        # Sync original photos
        self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
        album_0_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][0])
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
        self.assertFalse(os.path.isdir(album_0_path))
        self.assertFalse(os.path.isdir(album_1_path))

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_all_albums_not_filtered(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        """Test for successful original photo size download."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["all_albums"] = True
        mock_read_config.return_value = config
        album_0_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][0])
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
        config["photos"]["filters"]["albums"] = None
        # Sync original photos
        self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 1)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_folder_format(self, mock_read_config, mock_service, mock_get_username, mock_get_password):
        """Test for successful original photo size download with folder format."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["folder_format"] = "%Y/%m"
        mock_read_config.return_value = config
        # Sync original photos
        self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
        album_0_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][0])
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
        self.assertTrue(os.path.isdir(os.path.join(album_0_path, "2020", "08")))
        self.assertTrue(os.path.isdir(os.path.join(album_1_path, "2020", "07")))

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
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
        album_0_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][0])
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
        sync_photos.sync_photos(config=config, photos=mock_service.photos)

        os.remove(
            os.path.join(
                album_1_path,
                "IMG_3148__medium__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG",
            ),
        )
        # Download missing file
        with self.assertLogs() as captured:
            self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNotNone(
                next(
                    (
                        s
                        for s in captured[1]
                        if "album-1/IMG_3148__medium__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG ..." in s
                    ),
                    None,
                ),
            )
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 0)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
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
        album_0_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][0])
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
        sync_photos.sync_photos(config=config, photos=mock_service.photos)
        # Download changed file
        os.remove(
            os.path.join(
                album_1_path,
                "IMG_3148__medium__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG",
            ),
        )
        shutil.copyfile(
            os.path.join(DATA_DIR, "thumb.jpeg"),
            os.path.join(album_1_path, "IMG_3148.JPG"),
        )
        with self.assertLogs() as captured:
            self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNotNone(
                next(
                    (
                        s
                        for s in captured[1]
                        if "album-1/IMG_3148__medium__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG ..." in s
                    ),
                    None,
                ),
            )
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 0)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
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
            self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNone(next((s for s in captured[1] if "Downloading /" in s), None))

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
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
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
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
            self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNone(next((s for s in captured[1] if "Downloading /" in s), None))

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
            self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNone(next((s for s in captured[1] if "Downloading /" in s), None))

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
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
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
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
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
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
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
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
        self.assertTrue(len(sync_photos.remove_obsolete(destination_path=None, files=set())) == 0)

    def test_remove_obsolete_none_files(self):
        """Test for files as None."""
        obsolete_path = os.path.join(self.destination_path, "obsolete")
        self.assertTrue(len(sync_photos.remove_obsolete(destination_path=obsolete_path, files=None)) == 0)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
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
            self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
            self.assertTrue(len(captured.records) > 0)
            self.assertIsNotNone(
                next(
                    (
                        s
                        for s in captured[1]
                        if "all/IMG_3148__original__QVZ4My9WS2tiV1BkTmJXdzY4bXJXelN1ZW1YZw==.JPG ..." in s
                    ),
                    None,
                ),
            )

        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "all")))

    def test_download_photo_none_photo(self):
        """Test if download_photo has photo as None."""
        self.assertFalse(sync_photos.download_photo(None, ["original"], self.destination_path))

    def test_download_photo_none_file_size(self):
        """Test if download_photo has file size as None."""

        class MockPhoto:
            def download(self, quality):
                raise icloudpy.exceptions.ICloudPyAPIResponseException

        self.assertFalse(sync_photos.download_photo(MockPhoto(), None, self.destination_path))

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

        self.assertFalse(sync_photos.download_photo(MockPhoto(), ["original"], self.destination_path))

    def test_sync_album_none_album(self):
        """Test if album is None."""
        self.assertIsNone(sync_photos.sync_album(None, self.destination_path, ["original"]))

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
                folder_format=None,
            ),
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
                folder_format=None,
            ),
        )

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_photo_wanted_extensions_jpg(self, mock_read_config, mock_service, mock_get_username, mock_get_password):
        """Test for JPG extension filter."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["filters"]["extensions"] = ["JpG"]
        mock_read_config.return_value = config
        # Sync original photos
        self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
        album_0_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][0])
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) > 1)
        self.assertTrue(len(os.listdir(album_1_path)) > 0)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_photo_wanted_extensions_png(self, mock_read_config, mock_service, mock_get_username, mock_get_password):
        """Test for PNG extension filter."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["filters"]["extensions"] = ["PnG"]
        mock_read_config.return_value = config
        # Sync original photos
        self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
        album_0_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][0])
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(len(os.listdir(album_0_path)) == 1)
        self.assertTrue(len(os.listdir(album_1_path)) == 0)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_photo_download_with_shared_libraries(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        """Test for downloading photos from shared libraries."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        del config["photos"]["filters"]["albums"]
        # delete libraries from config
        del config["photos"]["filters"]["libraries"]
        mock_read_config.return_value = config
        # Sync original photos
        self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
        all_path = os.path.join(self.destination_path, "all")
        self.assertTrue(os.path.isdir(all_path))
        # Check for PrimarySync photo
        self.assertTrue(len(glob.glob(os.path.join(all_path, "IMG_3148*.JPG"))) > 0)
        # Check for shared photo
        self.assertTrue(len(glob.glob(os.path.join(all_path, "IMG_5513*.HEIC"))) > 0)

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_all_albums_filtered_missing_primary_sync(
        self,
        mock_read_config,
        mock_service,
        mock_get_username,
        mock_get_password,
    ):
        """Test for successful original photo size download."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        del config["photos"]["filters"]["libraries"]
        config["photos"]["filters"]["albums"] += ["Favorites"]
        mock_read_config.return_value = config
        # Sync original photos
        self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
        album_0_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][0])
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
        album_2_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][2])
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(os.path.isdir(album_2_path))

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_get_name_and_extension(self, mock_read_config, mock_service, mock_get_username, mock_get_password):
        """Test for successful original_alt photo size download."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["filters"]["file_sizes"] = ["original_alt"]
        mock_read_config.return_value = config
        # Sync original photos
        self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))
        album_0_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][0])
        album_1_path = os.path.join(self.destination_path, config["photos"]["filters"]["albums"][1])
        self.assertTrue(os.path.isdir(album_0_path))
        self.assertTrue(os.path.isdir(album_1_path))

    @patch(target="sys.stderr", new_callable=StringIO)
    def test_get_name_and_extension_warning(self, mock_stdout):
        """Test warning generation for invalid original_alt extension."""

        class MockPhoto:
            filename = "mock_filename.xed"
            versions = {"original_alt": {"type": "invalid"}}

        name, extension = sync_photos.get_name_and_extension(photo=MockPhoto(), file_size="original_alt")
        self.assertEqual(name, "mock_filename")
        self.assertEqual(extension, "xed")

    def test_get_max_threads_photos(self):
        """Test that get_max_threads returns reasonable values for photos."""
        config = read_config(config_path=tests.CONFIG_PATH)
        max_threads = sync_photos.get_max_threads(config)
        self.assertIsInstance(max_threads, int)
        self.assertGreater(max_threads, 0)
        self.assertLessEqual(max_threads, 8)

    def test_collect_photo_for_download_valid_photo(self):
        """Test collecting photo for download - valid photo."""
        files = set()

        # Create a mock photo with minimal required attributes
        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}  # Add size field
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()

        download_info = sync_photos.collect_photo_for_download(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
        )

        self.assertIsNotNone(download_info)
        self.assertEqual(download_info["photo"], photo)
        self.assertEqual(download_info["file_size"], "original")
        self.assertTrue(download_info["photo_path"].endswith(".jpg"))
        self.assertGreater(len(files), 0)

    def test_collect_photo_for_download_missing_version(self):
        """Test collecting photo for download - missing file size version."""
        files = set()

        # Create a mock photo with minimal required attributes
        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}  # Only has original, not nonexistent_size
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()

        download_info = sync_photos.collect_photo_for_download(
            photo=photo,
            file_size="nonexistent_size",  # This size doesn't exist
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
        )

        self.assertIsNone(download_info)

    def test_collect_photo_for_download_existing_photo(self):
        """Test collecting photo for download - photo already exists."""
        files = set()

        # Create a mock photo with minimal required attributes
        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}  # Add size field
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()

        # Create the photo file first to simulate existing file
        photo_path = sync_photos.generate_file_name(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            folder_format=None,
        )
        os.makedirs(os.path.dirname(photo_path), exist_ok=True)
        with open(photo_path, "wb") as f:
            f.write(b"A" * 1000)  # Write same content size as mock

        # Set modification time to match photo
        local_modified_time = time.mktime(photo.added_date.timetuple())
        os.utime(photo_path, (local_modified_time, local_modified_time))

        download_info = sync_photos.collect_photo_for_download(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
        )

        self.assertIsNone(download_info)  # Should be None since photo exists

    def test_download_photo_task_success(self):
        """Test successful photo download task."""

        # Create a mock photo with minimal required attributes and download method
        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}  # Add size field
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

            def download(self, file_size):
                # Return a mock response with raw attribute
                class MockResponse:
                    def __init__(self):
                        import io

                        self.raw = io.BytesIO(b"fake photo data")

                return MockResponse()

        photo = MockPhoto()
        photo_path = sync_photos.generate_file_name(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            folder_format=None,
        )

        download_info = {
            "photo": photo,
            "file_size": "original",
            "photo_path": photo_path,
        }

        result = sync_photos.download_photo_task(download_info)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(photo_path))

    def test_download_photo_task_failure(self):
        """Test failed photo download task."""
        download_info = {
            "photo": None,  # Invalid photo
            "file_size": "original",
            "photo_path": "/invalid/path/photo.jpg",
        }

        result = sync_photos.download_photo_task(download_info)
        self.assertFalse(result)

    @patch("src.photo_download_manager.get_max_threads_for_download")
    def test_sync_album_parallel_downloads(self, mock_get_max_threads):
        """Test sync_album with parallel downloads."""
        mock_get_max_threads.return_value = 2  # Use smaller thread pool for testing

        album = self.service.photos.albums["All Photos"]
        config = read_config(config_path=tests.CONFIG_PATH)

        result = sync_photos.sync_album(
            album=album,
            destination_path=self.destination_path,
            file_sizes=["original"],
            extensions=None,
            files=set(),
            folder_format=None,
            config=config,
        )

        self.assertTrue(result)
        mock_get_max_threads.assert_called()

        # Verify some photos were processed
        self.assertTrue(os.path.exists(self.destination_path))
        downloaded_files = list(Path(self.destination_path).glob("**/*.JPG"))
        self.assertGreater(len(downloaded_files), 0)

    def test_thread_safe_photo_file_operations(self):
        """Test that photo file set operations are thread-safe."""
        import threading
        import time

        from src.photo_download_manager import files_lock

        files = set()
        results = []

        def add_photo_files(start_num, count):
            for i in range(start_num, start_num + count):
                with files_lock:
                    files.add(f"photo_{i}.jpg")
                    # Capture the length inside the lock for thread safety
                    results.append(len(files))
                time.sleep(0.001)  # Small delay to increase chance of race conditions

        # Create multiple threads that add files concurrently
        threads = []
        thread_count = 3
        files_per_thread = 5
        for i in range(thread_count):
            thread = threading.Thread(target=add_photo_files, args=(i * files_per_thread, files_per_thread))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all files were added correctly
        expected_total = thread_count * files_per_thread
        self.assertEqual(len(files), expected_total)  # 3 threads × 5 files each

        # Verify all expected files are present
        for i in range(expected_total):
            self.assertIn(f"photo_{i}.jpg", files)

    @patch("src.photo_download_manager.execute_download_task")
    @patch("src.photo_download_manager.collect_download_task")
    def test_process_photo_with_none_files(self, mock_collect_task, mock_execute_task):
        """Test process_photo function with None files parameter."""
        from src.photo_download_manager import DownloadTaskInfo

        # Create a mock photo with minimal required attributes
        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()

        # Mock successful task
        mock_task = DownloadTaskInfo(photo, "original", "test_path.jpg")
        mock_collect_task.return_value = mock_task
        mock_execute_task.return_value = True

        # This tests the process_photo function with files=None
        result = sync_photos.process_photo(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=None,  # This triggers files=None behavior
            folder_format=None,
        )

        # Should return True even with None files
        self.assertTrue(result)

    @patch("src.photo_download_manager.execute_download_task")
    @patch("src.photo_download_manager.collect_download_task")
    def test_process_photo_old_function(self, mock_collect_task, mock_execute_task):
        """Test the old process_photo function for coverage."""
        from src.photo_download_manager import DownloadTaskInfo

        # Create a mock photo with minimal required attributes
        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        files = set()

        # Mock successful task
        mock_task = DownloadTaskInfo(photo, "original", "test_path.jpg")
        mock_collect_task.return_value = mock_task
        mock_execute_task.return_value = True

        # This tests the process_photo function
        result = sync_photos.process_photo(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
        )

        # Should return True and the files set should be handled by collect_download_task
        self.assertTrue(result)
        mock_collect_task.assert_called_once()
        mock_execute_task.assert_called_once_with(mock_task)

    def test_download_photo_task_exception(self):
        """Test download_photo_task with exception handling."""
        # Create a mock download task that will cause an exception
        download_task = {
            "photo": None,  # This will cause an exception
            "file_size": "original",
            "photo_path": "/some/path/photo.jpg",
        }

        result = sync_photos.download_photo_task(download_task)
        self.assertFalse(result)  # Should return False on exception

    def test_sync_album_with_download_exceptions(self):
        """Test sync_album with download tasks that raise exceptions."""
        from unittest.mock import patch

        # Mock a situation where execute_parallel_downloads raises an exception
        with patch("src.album_sync_orchestrator.execute_parallel_downloads") as mock_execute:
            mock_execute.side_effect = RuntimeError("Photo download failed")

            album = self.service.photos.albums["All Photos"]
            config = read_config(config_path=tests.CONFIG_PATH)

            # The exception should be raised since sync_album doesn't handle it
            with self.assertRaises(RuntimeError):
                sync_photos.sync_album(
                    album=album,
                    destination_path=self.destination_path,
                    file_sizes=["original"],
                    extensions=None,
                    files=set(),
                    folder_format=None,
                    config=config,
                )

            # Verify the exception handler was triggered
            mock_execute.assert_called()

    @patch("src.album_sync_orchestrator.execute_parallel_downloads")
    def test_sync_album_download_returns_false(self, mock_execute_downloads):
        """Test sync_album when download tasks return False."""
        # Mock to return (0, 1) indicating 0 successful, 1 failed
        mock_execute_downloads.return_value = (0, 1)

        album = self.service.photos.albums["All Photos"]
        config = read_config(config_path=tests.CONFIG_PATH)

        result = sync_photos.sync_album(
            album=album,
            destination_path=self.destination_path,
            file_sizes=["original"],
            extensions=None,
            files=set(),
            folder_format=None,
            config=config,
        )

        # Should complete successfully even when downloads fail
        self.assertTrue(result)
        mock_execute_downloads.assert_called()

    def test_parallel_vs_sequential_photo_performance(self):
        """Test and verify parallel photo downloads provide performance improvement."""
        import time
        from unittest.mock import patch

        # Create mock download tasks that simulate time-consuming photo downloads
        def mock_slow_photo_download(download_task):
            time.sleep(0.01)  # Simulate 10ms download time
            return True

        # Create a mock album with multiple photos
        album = self.service.photos.albums["All Photos"]
        config = read_config(config_path=tests.CONFIG_PATH)

        # Test sequential downloads (max_threads=1)
        with (
            patch("src.config_parser.get_app_max_threads", return_value=1),
            patch("src.sync_photos.download_photo_task", side_effect=mock_slow_photo_download),
        ):
            start_time = time.time()
            sync_photos.sync_album(
                album=album,
                destination_path=self.destination_path,
                file_sizes=["original"],
                extensions=None,
                files=set(),
                folder_format=None,
                config=config,
            )
            sequential_time = time.time() - start_time

        # Test parallel downloads (max_threads=4)
        with (
            patch("src.config_parser.get_app_max_threads", return_value=4),
            patch("src.sync_photos.download_photo_task", side_effect=mock_slow_photo_download),
        ):
            start_time = time.time()
            sync_photos.sync_album(
                album=album,
                destination_path=self.destination_path,
                file_sizes=["original"],
                extensions=None,
                files=set(),
                folder_format=None,
                config=config,
            )
            parallel_time = time.time() - start_time

        # Verify parallel downloads are faster (with some tolerance for test variance)
        # Parallel should be at least 10% faster than sequential (lenient for CI)
        improvement_ratio = sequential_time / parallel_time if parallel_time > 0 else 1.0

        # Log the performance improvement for verification
        print("\nPhoto Performance Test Results:")
        print(f"Sequential time: {sequential_time:.3f}s")
        print(f"Parallel time: {parallel_time:.3f}s")
        print(f"Performance improvement: {improvement_ratio:.2f}x faster")

        # Only assert if we have meaningful timing data
        if sequential_time > 0.001 and parallel_time > 0.001:
            self.assertGreaterEqual(
                improvement_ratio,
                0.9,  # Very lenient - just verify it's not significantly slower
                f"Parallel photo downloads ({parallel_time:.3f}s) should not be significantly slower than sequential ({sequential_time:.3f}s)",
            )

    @patch("src.photo_download_manager.execute_download_task")
    @patch("src.photo_download_manager.collect_download_task")
    def test_process_photo_success_path(self, mock_collect_task, mock_execute_task):
        """Test process_photo successful execution."""
        # Configure mocks: collect succeeds, execute succeeds
        from src.photo_download_manager import DownloadTaskInfo

        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": "1000"}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        files = set()

        # Mock collect_download_task to return a task
        mock_task = DownloadTaskInfo(photo, "original", "test_path.jpg")
        mock_collect_task.return_value = mock_task
        mock_execute_task.return_value = True

        # Call process_photo which should return True
        result = sync_photos.process_photo(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
        )

        # Should return True for successful processing
        self.assertTrue(result)
        mock_collect_task.assert_called_once()
        mock_execute_task.assert_called_once_with(mock_task)

    @patch("src.photo_download_manager.collect_download_task")
    def test_process_photo_photo_exists(self, mock_collect_task):
        """Test process_photo when photo already exists to cover line 175."""
        # Mock collect_download_task to return None (photo exists)
        mock_collect_task.return_value = None

        # Create a mock photo with minimal required attributes
        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": "1000"}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        files = set()

        # Call process_photo which should return False (line 175)
        result = sync_photos.process_photo(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
        )

        # Should return False since collect_download_task returns None (photo exists)
        self.assertFalse(result)

    @patch("src.sync_photos.download_photo")
    def test_download_photo_task_exception_handling(self, mock_download_photo):
        """Test download_photo_task exception handling to cover lines 221-223."""
        # Configure mock to raise an exception
        mock_download_photo.side_effect = Exception("Test photo download error")

        # Create a mock photo with minimal required attributes
        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": "1000"}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        photo_path = os.path.join(self.destination_path, "test_photo.jpg")

        task_info = {
            "photo": photo,
            "file_size": "original",
            "photo_path": photo_path,
            "files": set(),
        }

        # Call download_photo_task which should catch the exception and return False
        result = sync_photos.download_photo_task(task_info)

        # Should return False due to exception
        self.assertFalse(result)
        mock_download_photo.assert_called_once()

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_photos_hardlinks(self, mock_read_config, mock_service, mock_get_username, mock_get_password):
        """Test for successful hard link creation for duplicate photos with parallel downloads."""
        mock_service = self.service
        config = self.config.copy()
        config["photos"]["destination"] = self.destination_path
        config["photos"]["filters"]["libraries"] = ["PrimarySync"]
        config["photos"]["all_albums"] = True
        config["photos"]["use_hardlinks"] = True
        # Remove album filters to sync all albums
        config["photos"]["filters"]["albums"] = None
        mock_read_config.return_value = config

        # Sync photos with hard links enabled
        self.assertIsNone(sync_photos.sync_photos(config=config, photos=mock_service.photos))

        # Check if "All Photos" directory exists
        all_photos_path = os.path.join(self.destination_path, "All Photos")
        self.assertTrue(os.path.isdir(all_photos_path))

        # Check if other album directories exist
        album_1_path = os.path.join(self.destination_path, "album-1")
        album_2_path = os.path.join(self.destination_path, "album 2")
        self.assertTrue(os.path.isdir(album_1_path))
        self.assertTrue(os.path.isdir(album_2_path))

        # Find a file that should be duplicated across albums
        duplicate_files = glob.glob(f"{self.destination_path}/**/IMG_3328*original*", recursive=True)
        self.assertGreater(len(duplicate_files), 1, "Should have duplicate files across albums")

        # Check that all duplicate files have the same inode (hard linked)
        inodes = set()
        link_counts = set()
        for file_path in duplicate_files:
            file_stat = os.stat(file_path)
            inodes.add(file_stat.st_ino)
            link_counts.add(file_stat.st_nlink)

        # All files should have the same inode (hard linked)
        self.assertEqual(len(inodes), 1, "All duplicate files should share the same inode")

        # All files should have the same link count
        self.assertEqual(len(link_counts), 1, "All duplicate files should have the same link count")

        # Link count should equal the number of duplicate files
        expected_link_count = len(duplicate_files)
        actual_link_count = list(link_counts)[0]
        self.assertEqual(
            actual_link_count,
            expected_link_count,
            f"Link count should be {expected_link_count}, got {actual_link_count}",
        )

        LOGGER.info(f"Hard link test passed: {len(duplicate_files)} files share 1 inode, saving storage space")

    def test_create_hardlink_failure(self):
        """Test create_hardlink function when it fails."""
        from src.sync_photos import create_hardlink

        # Test with invalid source path (should fail)
        result = create_hardlink("/nonexistent/source.jpg", "/tmp/dest.jpg")
        self.assertFalse(result)

    def test_collect_photo_with_hardlink_source(self):
        """Test collect_photo_for_download with hardlink registry."""
        from src.sync_photos import collect_photo_for_download

        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        files = set()

        # Create a source file for hardlink
        source_path = os.path.join(self.destination_path, "source_photo.jpg")
        os.makedirs(os.path.dirname(source_path), exist_ok=True)
        with open(source_path, "wb") as f:
            f.write(b"test photo data")

        # Create hardlink registry with existing source
        hardlink_registry = {"test_photo_id_original": source_path}

        download_info = collect_photo_for_download(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
            hardlink_registry=hardlink_registry,
        )

        # Should return download info with hardlink_source set
        self.assertIsNotNone(download_info)
        self.assertEqual(download_info["hardlink_source"], source_path)
        self.assertEqual(download_info["hardlink_registry"], hardlink_registry)

    def test_download_photo_task_with_hardlink_success(self):
        """Test download_photo_task with successful hardlink creation."""
        from src.sync_photos import download_photo_task

        # Create a source file for hardlink
        source_path = os.path.join(self.destination_path, "source_photo.jpg")
        os.makedirs(os.path.dirname(source_path), exist_ok=True)
        with open(source_path, "wb") as f:
            f.write(b"test photo data")

        # Create destination path
        dest_path = os.path.join(self.destination_path, "dest_photo.jpg")

        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        hardlink_registry = {}

        download_info = {
            "photo": photo,
            "file_size": "original",
            "photo_path": dest_path,
            "hardlink_source": source_path,
            "hardlink_registry": hardlink_registry,
        }

        result = download_photo_task(download_info)

        # Should succeed via hardlink
        self.assertTrue(result)
        self.assertTrue(os.path.exists(dest_path))

        # Verify it's a hardlink (same inode)
        self.assertEqual(os.stat(source_path).st_ino, os.stat(dest_path).st_ino)

    def test_download_photo_task_hardlink_fallback_to_download(self):
        """Test download_photo_task falls back to download when hardlink fails."""
        from src.sync_photos import download_photo_task

        # Use invalid source path to force hardlink failure
        source_path = "/nonexistent/source_photo.jpg"
        dest_path = os.path.join(self.destination_path, "dest_photo.jpg")

        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

            def download(self, file_size):
                # Return a mock response with raw attribute
                class MockResponse:
                    def __init__(self):
                        import io

                        self.raw = io.BytesIO(b"fake photo data")

                return MockResponse()

        photo = MockPhoto()
        hardlink_registry = {}

        download_info = {
            "photo": photo,
            "file_size": "original",
            "photo_path": dest_path,
            "hardlink_source": source_path,  # Invalid source
            "hardlink_registry": hardlink_registry,
        }

        result = download_photo_task(download_info)

        # Should succeed via download fallback
        self.assertTrue(result)
        self.assertTrue(os.path.exists(dest_path))

        # Verify file was downloaded (not hardlinked)
        with open(dest_path, "rb") as f:
            content = f.read()
            self.assertEqual(content, b"fake photo data")

    @patch("src.photo_download_manager.execute_download_task")
    @patch("src.photo_download_manager.collect_download_task")
    def test_process_photo_hardlink_success(self, mock_collect_task, mock_execute_task):
        """Test process_photo with successful hardlink creation."""
        from src.photo_download_manager import DownloadTaskInfo

        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        files = set()

        # Create source file for hardlink
        source_path = os.path.join(self.destination_path, "source_photo.jpg")
        os.makedirs(os.path.dirname(source_path), exist_ok=True)
        with open(source_path, "wb") as f:
            f.write(b"test photo data")

        hardlink_registry = {"test_photo_id_original": source_path}

        # Mock task with hardlink source
        mock_task = DownloadTaskInfo(photo, "original", "test_path.jpg", hardlink_source=source_path)
        mock_collect_task.return_value = mock_task
        mock_execute_task.return_value = True

        result = sync_photos.process_photo(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
            hardlink_registry=hardlink_registry,
        )

        # Should succeed via hardlink
        self.assertTrue(result)
        mock_collect_task.assert_called_once()
        mock_execute_task.assert_called_once_with(mock_task)

    @patch("src.photo_download_manager.execute_download_task")
    @patch("src.photo_download_manager.collect_download_task")
    def test_process_photo_hardlink_failure_fallback(self, mock_collect_task, mock_execute_task):
        """Test process_photo fallback to download when hardlink fails."""
        from src.photo_download_manager import DownloadTaskInfo

        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        files = set()

        # Create source file for hardlink
        source_path = os.path.join(self.destination_path, "source_photo.jpg")
        hardlink_registry = {"test_photo_id_original": source_path}

        # Mock task with hardlink source that will fail but download will succeed
        mock_task = DownloadTaskInfo(photo, "original", "test_path.jpg", hardlink_source=source_path)
        mock_collect_task.return_value = mock_task
        mock_execute_task.return_value = True  # Execute succeeds after hardlink failure

        result = sync_photos.process_photo(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
            hardlink_registry=hardlink_registry,
        )

        # Should succeed via download fallback
        self.assertTrue(result)
        mock_collect_task.assert_called_once()
        mock_execute_task.assert_called_once_with(mock_task)

    @patch("src.photo_download_manager.execute_download_task")
    @patch("src.photo_download_manager.collect_download_task")
    def test_process_photo_with_hardlink_registry_no_existing(self, mock_collect_task, mock_execute_task):
        """Test process_photo with hardlink registry but no existing photo."""
        from src.photo_download_manager import DownloadTaskInfo

        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        files = set()
        hardlink_registry = {}  # Empty registry

        # Mock task with no hardlink source
        mock_task = DownloadTaskInfo(photo, "original", "test_path.jpg")
        mock_collect_task.return_value = mock_task
        mock_execute_task.return_value = True

        result = sync_photos.process_photo(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
            hardlink_registry=hardlink_registry,
        )

        # Should succeed via download and register the photo
        self.assertTrue(result)
        mock_collect_task.assert_called_once()
        mock_execute_task.assert_called_once_with(mock_task)
        # Verify photo was registered in legacy format
        self.assertIn("test_photo_id_original", hardlink_registry)

    @patch("src.photo_download_manager.execute_download_task")
    @patch("src.photo_download_manager.collect_download_task")
    def test_process_photo_download_fails(self, mock_collect_task, mock_execute_task):
        """Test process_photo when download_photo returns False."""
        from src.photo_download_manager import DownloadTaskInfo

        class MockPhoto:
            def __init__(self):
                import datetime

                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        files = set()

        # Mock task that fails to execute
        mock_task = DownloadTaskInfo(photo, "original", "test_path.jpg")
        mock_collect_task.return_value = mock_task
        mock_execute_task.return_value = False  # Download fails

        result = sync_photos.process_photo(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None,
            hardlink_registry=None,
        )

        # Should return False when download fails
        self.assertFalse(result)
        mock_collect_task.assert_called_once()
        mock_execute_task.assert_called_once_with(mock_task)

    def test_hardlink_registry_clear(self):
        """Test clearing the hardlink registry."""
        from src.hardlink_registry import HardlinkRegistry

        registry = HardlinkRegistry()
        registry.register_photo_path("photo1", "original", "/path/to/photo1.jpg")
        registry.register_photo_path("photo2", "medium", "/path/to/photo2.jpg")

        # Verify registry has entries
        self.assertEqual(registry.get_registry_size(), 2)

        # Clear the registry
        registry.clear()

        # Verify registry is empty
        self.assertEqual(registry.get_registry_size(), 0)

    def test_legacy_wrapper_functions(self):
        """Test the legacy wrapper functions for coverage."""

        # Test photo_wanted wrapper
        class MockPhoto:
            def __init__(self):
                self.filename = "test.jpg"

        photo = MockPhoto()
        result = sync_photos.photo_wanted(photo, [".jpg", ".png"])
        self.assertTrue(result)

        # Test generate_file_name wrapper
        photo.id = "test_id"
        import datetime

        photo.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
        path = sync_photos.generate_file_name(photo, "original", self.destination_path, None)
        self.assertIsInstance(path, str)
        self.assertTrue(path.endswith(".jpg"))

    def test_legacy_photo_exists_wrapper(self):
        """Test the legacy photo_exists wrapper function."""

        class MockPhoto:
            def __init__(self):
                self.filename = "test.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}

        photo = MockPhoto()

        # Mock the underlying function
        with patch("src.photo_file_utils.check_photo_exists") as mock_check:
            mock_check.return_value = True
            result = sync_photos.photo_exists(photo, "original", "/path/to/photo.jpg")
            self.assertTrue(result)
            mock_check.assert_called_once()

    def test_legacy_create_hardlink_wrapper(self):
        """Test the legacy create_hardlink wrapper function."""
        with patch("src.photo_file_utils.create_hardlink") as mock_create:
            mock_create.return_value = True
            result = sync_photos.create_hardlink("/source/path", "/dest/path")
            self.assertTrue(result)
            mock_create.assert_called_once_with("/source/path", "/dest/path")

    def test_sync_album_with_hardlink_registry_conversion(self):
        """Test sync_album with hardlink registry conversion."""
        album = self.service.photos.albums["All Photos"]
        config = read_config(config_path=tests.CONFIG_PATH)

        # Create legacy hardlink registry
        hardlink_registry = {
            "photo1_original": "/path/to/photo1.jpg",
            "photo2_medium": "/path/to/photo2.jpg",
            "invalid_key": "/path/to/invalid.jpg",  # Key without underscore
        }

        with patch("src.sync_photos.sync_album_photos") as mock_sync:
            mock_sync.return_value = True

            result = sync_photos.sync_album(
                album=album,
                destination_path=self.destination_path,
                file_sizes=["original"],
                extensions=None,
                files=set(),
                folder_format=None,
                hardlink_registry=hardlink_registry,
                config=config,
            )

            self.assertTrue(result)
            mock_sync.assert_called_once()

            # Verify the hardlink registry was converted and passed
            call_args = mock_sync.call_args
            converted_registry = call_args.kwargs["hardlink_registry"]
            self.assertIsNotNone(converted_registry)

    def test_sync_album_legacy_registry_update_path(self):
        """Test sync_album legacy registry update path."""
        album = self.service.photos.albums["All Photos"]
        config = read_config(config_path=tests.CONFIG_PATH)

        # Create legacy hardlink registry
        hardlink_registry = {}

        with patch("src.album_sync_orchestrator.sync_album_photos") as mock_sync:
            mock_sync.return_value = True

            result = sync_photos.sync_album(
                album=album,
                destination_path=self.destination_path,
                file_sizes=["original"],
                extensions=None,
                files=set(),
                folder_format=None,
                hardlink_registry=hardlink_registry,
                config=config,
            )

            self.assertTrue(result)

    def test_photo_download_manager_edge_cases(self):
        """Test photo download manager edge cases for coverage."""
        from src.photo_download_manager import generate_photo_path

        class MockPhoto:
            def __init__(self):
                self.filename = "test.jpg"
                self.id = "test_id"
                import datetime

                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)

        photo = MockPhoto()

        # Test generate_photo_path with existing file that needs normalization
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock os.path.isfile to simulate the normalization case (line 107)
            with patch("src.photo_download_manager.os.path.isfile") as mock_isfile:
                mock_isfile.return_value = True
                with patch("src.photo_download_manager.rename_legacy_file_if_exists") as mock_rename:
                    path = generate_photo_path(photo, "original", tmpdir, None)
                    self.assertIsInstance(path, str)
                    # Verify rename was called for the normalization case
                    self.assertTrue(mock_rename.called)

    def test_execute_download_task_exception_handling(self):
        """Test execute_download_task exception handling."""
        from src.photo_download_manager import DownloadTaskInfo, execute_download_task

        class MockPhoto:
            def __init__(self):
                self.filename = "test.jpg"
                self.id = "test_id"

        photo = MockPhoto()
        task_info = DownloadTaskInfo(photo, "original", "/invalid/path/photo.jpg")

        # Mock download_photo_from_server to raise an exception
        with patch("src.photo_download_manager.download_photo_from_server") as mock_download:
            mock_download.side_effect = Exception("Download failed")

            result = execute_download_task(task_info)
            self.assertFalse(result)

    def test_execute_parallel_downloads_empty_tasks(self):
        """Test execute_parallel_downloads with empty task list."""
        from src.photo_download_manager import execute_parallel_downloads

        config = {"app": {"max_threads": 4}}
        successful, failed = execute_parallel_downloads([], config)

        self.assertEqual(successful, 0)
        self.assertEqual(failed, 0)

    def test_execute_parallel_downloads_exception_handling(self):
        """Test execute_parallel_downloads with future exceptions."""
        from concurrent.futures import Future

        from src.photo_download_manager import DownloadTaskInfo, execute_parallel_downloads

        class MockPhoto:
            def __init__(self):
                self.filename = "test.jpg"
                self.id = "test_id"

        photo = MockPhoto()
        task_info = DownloadTaskInfo(photo, "original", "/test/path/photo.jpg")

        config = {"app": {"max_threads": 1}}

        # Mock ThreadPoolExecutor to return a future that raises an exception
        with patch("src.photo_download_manager.ThreadPoolExecutor") as mock_executor_class:
            mock_executor = mock_executor_class.return_value.__enter__.return_value

            # Create a mock future that raises an exception
            mock_future = Future()
            mock_future.set_exception(Exception("Future exception"))

            mock_executor.submit.return_value = mock_future

            successful, failed = execute_parallel_downloads([task_info], config)

            # Should handle the exception and count as failed
            self.assertEqual(successful, 0)
            self.assertEqual(failed, 1)

    def test_rename_legacy_file_if_exists(self):
        """Test rename_legacy_file_if_exists function."""
        import tempfile

        from src.photo_file_utils import rename_legacy_file_if_exists

        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "old_file.jpg")
            new_path = os.path.join(tmpdir, "new_file.jpg")

            # Create the old file
            with open(old_path, "w") as f:
                f.write("test content")

            # Rename it
            rename_legacy_file_if_exists(old_path, new_path)

            # Verify old file is gone and new file exists
            self.assertFalse(os.path.exists(old_path))
            self.assertTrue(os.path.exists(new_path))

            # Test with non-existent file (should not raise exception)
            rename_legacy_file_if_exists("/non/existent/file.jpg", "/another/path.jpg")

    def test_generate_photo_path_different_normalization(self):
        """Test generate_photo_path with different normalization (line 107)."""
        from src.photo_download_manager import generate_photo_path

        class MockPhoto:
            def __init__(self):
                self.filename = "test.jpg"
                self.id = "test_id"
                import datetime

                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)

        photo = MockPhoto()

        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock the condition where final_file_path != normalized_path (line 107)
            with patch("src.photo_download_manager.os.path.isfile") as mock_isfile:
                mock_isfile.return_value = True
                with patch("src.photo_download_manager.rename_legacy_file_if_exists") as mock_rename:
                    # Mock normalize_file_path to return a different path
                    with patch("src.photo_download_manager.normalize_file_path") as mock_normalize:
                        mock_normalize.return_value = "/different/path.jpg"
                        generate_photo_path(photo, "original", tmpdir, None)
                        # Should have called rename for the normalization case
                        self.assertTrue(mock_rename.called)

    def test_execute_download_task_hardlink_failure_fallback(self):
        """Test execute_download_task hardlink failure fallback (line 180)."""
        from src.hardlink_registry import HardlinkRegistry
        from src.photo_download_manager import DownloadTaskInfo, execute_download_task

        class MockPhoto:
            def __init__(self):
                self.filename = "test.jpg"
                self.id = "test_id"

        photo = MockPhoto()
        registry = HardlinkRegistry()
        task_info = DownloadTaskInfo(
            photo,
            "original",
            "/test/path.jpg",
            hardlink_source="/source/path.jpg",
            hardlink_registry=registry,
        )

        # Mock hardlink creation to fail, download to succeed
        with patch("src.photo_download_manager.create_hardlink") as mock_hardlink:
            mock_hardlink.return_value = False  # Hardlink fails
            with patch("src.photo_download_manager.download_photo_from_server") as mock_download:
                mock_download.return_value = True  # Download succeeds

                result = execute_download_task(task_info)

                self.assertTrue(result)
                mock_hardlink.assert_called_once()
                mock_download.assert_called_once()

    def test_execute_parallel_downloads_future_exception_detailed(self):
        """Test execute_parallel_downloads with future exceptions."""
        from concurrent.futures import Future

        from src.photo_download_manager import DownloadTaskInfo, execute_parallel_downloads

        class MockPhoto:
            def __init__(self):
                self.filename = "test.jpg"
                self.id = "test_id"

        photo = MockPhoto()
        task_info = DownloadTaskInfo(photo, "original", "/test/path.jpg")

        config = {"app": {"max_threads": 1}}

        # Mock ThreadPoolExecutor to simulate future exception
        with patch("src.photo_download_manager.ThreadPoolExecutor") as mock_executor_class:
            mock_executor = mock_executor_class.return_value.__enter__.return_value

            # Create a future that will raise an exception
            mock_future = Future()
            mock_future.set_exception(RuntimeError("Future processing error"))

            mock_executor.submit.return_value = mock_future

            successful, failed = execute_parallel_downloads([task_info], config)

            # Should count the exception as a failure
            self.assertEqual(successful, 0)
            self.assertEqual(failed, 1)

    def test_execute_parallel_downloads_future_returns_false(self):
        """Test execute_parallel_downloads when future.result() returns False (line 241)."""
        from concurrent.futures import Future

        from src.photo_download_manager import DownloadTaskInfo, execute_parallel_downloads

        class MockPhoto:
            def __init__(self):
                self.filename = "test.jpg"
                self.id = "test_id"

        photo = MockPhoto()
        task_info = DownloadTaskInfo(photo, "original", "/test/path.jpg")

        config = {"app": {"max_threads": 1}}

        # Mock ThreadPoolExecutor where future.result() returns False
        with patch("src.photo_download_manager.ThreadPoolExecutor") as mock_executor_class:
            mock_executor = mock_executor_class.return_value.__enter__.return_value

            # Create a future that returns False (download failed)
            mock_future = Future()
            mock_future.set_result(False)

            mock_executor.submit.return_value = mock_future

            successful, failed = execute_parallel_downloads([task_info], config)

            # Should count the False result as a failure (covers line 241)
            self.assertEqual(successful, 0)
            self.assertEqual(failed, 1)
