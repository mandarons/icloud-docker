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
        max_threads = sync_photos.get_max_threads()
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

    @patch("src.sync_photos.get_max_threads")
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

        files = set()
        results = []

        def add_photo_files(start_num, count):
            for i in range(start_num, start_num + count):
                with sync_photos.files_lock:
                    files.add(f"photo_{i}.jpg")
                time.sleep(0.001)  # Small delay to increase chance of race conditions
            results.append(len(files))

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

    def test_process_photo_with_none_files(self):
        """Test process_photo function with None files parameter."""
        # Create a mock photo with minimal required attributes
        class MockPhoto:
            def __init__(self):
                import datetime
                self.filename = "test_photo.jpg"
                self.versions = {"original": {"type": "jpeg", "size": 1000}}
                self.added_date = datetime.datetime(2021, 1, 1, 12, 0, 0)
                self.id = "test_photo_id"

        photo = MockPhoto()
        
        # This tests line 175 (the old process_photo function with files=None)
        result = sync_photos.process_photo(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=None,  # This triggers line 175 behavior
            folder_format=None
        )
        
        # Should return True even with None files
        self.assertTrue(result)

    def test_process_photo_old_function(self):
        """Test the old process_photo function for coverage."""
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
        
        # This tests the old process_photo function (lines 172-177)
        result = sync_photos.process_photo(
            photo=photo,
            file_size="original",
            destination_path=self.destination_path,
            files=files,
            folder_format=None
        )
        
        # Should return True and add the photo path to files
        self.assertTrue(result)
        self.assertGreater(len(files), 0)

    def test_download_photo_task_exception(self):
        """Test download_photo_task with exception handling."""
        # Create a mock download task that will cause an exception
        download_task = {
            'photo': None,  # This will cause an exception
            'file_size': 'original',
            'photo_path': '/some/path/photo.jpg'
        }
        
        result = sync_photos.download_photo_task(download_task)
        self.assertFalse(result)  # Should return False on exception

    def test_sync_album_with_download_exceptions(self):
        """Test sync_album with download tasks that raise exceptions."""
        from unittest.mock import patch, MagicMock
        
        # Mock a situation where download_photo_task raises an exception
        with patch('src.sync_photos.download_photo_task') as mock_download:
            mock_download.side_effect = RuntimeError("Photo download failed")
            
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
            
            # Should complete successfully even with exceptions
            self.assertTrue(result)

    def test_parallel_vs_sequential_photo_performance(self):
        """Test and verify parallel photo downloads provide performance improvement."""
        import time
        from unittest.mock import patch, MagicMock
        
        # Create mock download tasks that simulate time-consuming photo downloads
        def mock_slow_photo_download(download_task):
            time.sleep(0.01)  # Simulate 10ms download time
            return True
        
        # Create a mock album with multiple photos
        album = self.service.photos.albums["All Photos"]
        config = read_config(config_path=tests.CONFIG_PATH)
        
        # Test sequential downloads (max_threads=1)
        with patch('src.config_parser.get_app_max_threads', return_value=1), \
             patch('src.sync_photos.download_photo_task', side_effect=mock_slow_photo_download):
            
            start_time = time.time()
            result = sync_photos.sync_album(
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
        with patch('src.config_parser.get_app_max_threads', return_value=4), \
             patch('src.sync_photos.download_photo_task', side_effect=mock_slow_photo_download):
            
            start_time = time.time()
            result = sync_photos.sync_album(
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
        # Parallel should be at least 25% faster than sequential
        improvement_ratio = sequential_time / parallel_time
        self.assertGreater(improvement_ratio, 1.25, 
                          f"Parallel photo downloads ({parallel_time:.3f}s) should be significantly faster than sequential ({sequential_time:.3f}s)")
        
        # Log the performance improvement for verification
        print(f"\nPhoto Performance Test Results:")
        print(f"Sequential time: {sequential_time:.3f}s")
        print(f"Parallel time: {parallel_time:.3f}s") 
        print(f"Performance improvement: {improvement_ratio:.2f}x faster")
