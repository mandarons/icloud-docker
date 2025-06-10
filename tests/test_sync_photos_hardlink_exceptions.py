import unittest
from unittest.mock import MagicMock, patch

from src import sync_photos


class TestSyncPhotosHardlinkExceptions(unittest.TestCase):
    def setUp(self):
        self.photo = MagicMock()
        self.photo.filename = "test.jpg"
        self.photo.versions = {"original": {"size": "100"}}
        self.photo.id = "photoid"
        self.photo.created = MagicMock(strftime=lambda fmt: "2025-06")
        self.file_size = "original"
        self.folder_format = None
        self.files = set()
        self.destination_path = "/tmp/album"
        self.all_photos_path = "/tmp/all"

    @patch("os.path.samefile", side_effect=OSError("Simulated samefile error"))
    @patch("os.path.exists", return_value=True)
    def test_compare_directories_exception(self, mock_exists, mock_samefile):
        # Should log a warning and continue to download_photo
        with (
            patch("src.sync_photos.generate_file_name", return_value="/tmp/all/test.jpg"),
            patch("src.sync_photos.photo_exists", return_value=False),
            patch("src.sync_photos.download_photo") as mock_download,
        ):
            sync_photos.process_photo(
                self.photo,
                self.file_size,
                self.destination_path,
                self.files,
                self.folder_format,
                self.all_photos_path,
            )
            mock_download.assert_called_once()

    @patch("os.path.samefile", return_value=False)
    @patch("os.path.exists", return_value=True)
    def test_hardlink_inner_exception(self, mock_exists, mock_samefile):
        # Simulate error in os.link
        with (
            patch("src.sync_photos.generate_file_name", return_value="/tmp/all/test.jpg"),
            patch("os.path.isfile", return_value=True),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
            patch("os.link", side_effect=OSError("Simulated link error")),
            patch("src.sync_photos.photo_exists", return_value=False),
            patch("src.sync_photos.download_photo") as mock_download,
        ):
            sync_photos.process_photo(
                self.photo,
                self.file_size,
                self.destination_path,
                self.files,
                self.folder_format,
                self.all_photos_path,
            )
            mock_download.assert_called_once()


if __name__ == "__main__":
    unittest.main()
