"""Tests for sync_drive.py file."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from icloudpy.exceptions import ICloudPyAPIResponseException

import tests
from src import LOGGER, read_config, sync_drive
from tests import DATA_DIR, data


class TestSyncDrive(unittest.TestCase):
    """Test class for sync_drive.py file."""

    def setUp(self) -> None:
        """Initialize tests."""
        self.config = read_config(config_path=tests.CONFIG_PATH)
        self.ignore = self.config["drive"]["ignore"]
        self.filters = self.config["drive"]["filters"]
        self.root = tests.DRIVE_DIR
        self.destination_path = self.root
        os.makedirs(self.destination_path, exist_ok=True)
        self.service = data.ICloudPyServiceMock(data.AUTHENTICATED_USER, data.VALID_PASSWORD)
        self.drive = self.service.drive
        self.items = self.drive.dir()
        self.folder_item = self.drive[self.items[5]]
        self.file_item = self.drive[self.items[4]]["Test"]["Scanned document 1.pdf"]
        self.package_item = self.drive[self.items[6]]["Sample"]["Project.band"]
        self.special_chars_package_item = self.drive[self.items[6]]["Sample"]["Fotoksiążka-Wzór.xmcf"]
        self.package_item_nested = self.drive[self.items[6]]["Sample"]["ms.band"]
        self.file_name = "Scanned document 1.pdf"
        self.package_name = "Project.band"
        self.package_name_nested = "ms.band"
        self.local_file_path = os.path.join(self.destination_path, self.file_name)
        self.local_package_path = os.path.join(self.destination_path, self.package_name)

    def tearDown(self) -> None:
        """Delete temp directory."""
        shutil.rmtree(tests.TEMP_DIR)

    def test_wanted_parent_folder_none_filters(self):
        """Test for wanted parent folder filters as None."""
        self.filters["folders"] = ["dir1/dir11"]
        self.assertTrue(
            sync_drive.wanted_parent_folder(
                filters=None,
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1/dir11"),
            ),
        )

    def test_wanted_parent_folder(self):
        """Test for a valid wanted parent folder."""
        self.filters["folders"] = ["dir1/dir11"]
        self.assertTrue(
            sync_drive.wanted_parent_folder(
                ignore=None,
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1/dir11/some/dirs/file.ext"),
            ),
        )

    def test_wanted_parent_folder_missing_parent_folder(self):
        """Test for missing parent folder."""
        self.filters["folders"] = ["dir1/dir11"]
        self.assertFalse(
            sync_drive.wanted_parent_folder(
                ignore=None,
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )

    def test_wanted_folder_single_variations(self):
        """Test for wanted folder variations."""
        self.filters["folders"] = ["dir1"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )
        self.filters["folders"] = ["/dir1"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )
        self.filters["folders"] = ["dir1/"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )
        self.filters["folders"] = ["/dir1/"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )

    def test_wanted_folder_single_path(self):
        """Test for wanted folder with single path."""
        self.filters["folders"] = ["dir1/dir2/dir3/", "dir1//dir2/dir3//"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2", "dir3"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir3"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir2"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir3"),
            ),
        )
        self.filters["folders"] = ["dir1//dir2/dir3//"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2", "dir3"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir3"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir2"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir3"),
            ),
        )

    def test_wanted_folder_multiple(self):
        """Test for multiple wanted folders."""
        self.filters["folders"] = ["dir1", "dir2"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir2"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir3"),
            ),
        )

    def test_wanted_folder_multiple_paths(self):
        """Test for wanted folder multiple paths."""
        self.filters["folders"] = ["dir1/dir2/dir3/", "dirA/dirB/dirC"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2", "dir3"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir3"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir2"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir3"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dirA"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dirA", "dirB"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dirA", "dirB", "dirC"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dirA", "dirC"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dirB"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters,
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dirC"),
            ),
        )

    def test_wanted_folder_ignore(self):
        """Tes for wanted folder ignore."""
        self.ignore = ["dir2/"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=None,
                ignore=self.ignore,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=None,
                ignore=self.ignore,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir3"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=None,
                ignore=self.ignore,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2", "dir3"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=None,
                ignore=self.ignore,
                root=self.root,
                folder_path=os.path.join(self.root, "dir2", "dir1"),
            ),
        )

    def test_wanted_folder_ignore_multiple_paths(self):
        """Test for wanted folder ignore multiple paths."""
        self.ignore = ["dir2/", "dir1/dir3/"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=None,
                ignore=self.ignore,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=None,
                ignore=self.ignore,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir4"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=None,
                ignore=self.ignore,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2", "dir3"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=None,
                ignore=["dir3"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir3"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=None,
                ignore=self.ignore,
                root=self.root,
                folder_path=os.path.join(self.root, "dir2", "dir1"),
            ),
        )

    def test_wanted_folder_ignore_takes_precedence_to_filters(self):
        """Test for wanted folder ignore takes precedence to filters."""
        self.ignore = ["dir2/"]
        self.filters["folders"] = ["dir2/"]
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=self.ignore,
                root=self.root,
                folder_path=os.path.join(self.root, "dir2", "dir3"),
            ),
        )

    def test_wanted_folder_empty(self):
        """Test for empty wanted folder."""
        original_filters = dict(self.filters)
        self.filters["folders"] = []
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            ),
        )
        self.filters = dict(original_filters)

    def test_wanted_folder_none_folder_path(self):
        """Test for wanted folder path as None."""
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
                folder_path=None,
            ),
        )

    def test_wanted_folder_none_filters(self):
        """Test for wanted folder filters as None."""
        self.assertTrue(sync_drive.wanted_folder(filters=None, ignore=None, root=self.root, folder_path="dir1"))

    def test_wanted_folder_none_root(self):
        """Test for wanted folder root as None."""
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                ignore=None,
                root=None,
                folder_path="dir1",
            ),
        )

    def test_wanted_file(self):
        """Test for a valid wanted file."""
        self.filters["file_extensions"] = ["py"]
        self.assertTrue(
            sync_drive.wanted_file(filters=self.filters["file_extensions"], ignore=None, file_path=__file__),
        )

    def test_wanted_file_missing(self):
        """Test for a missing wanted file."""
        self.assertFalse(
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"],
                ignore=None,
                file_path=tests.CONFIG_PATH,
            ),
        )

    def test_wanted_file_check_log(self):
        """Test for valid unwanted file."""
        with self.assertLogs(logger=LOGGER, level="DEBUG") as captured:
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"],
                ignore=None,
                file_path=tests.CONFIG_PATH,
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIn("Skipping the unwanted file", captured.records[0].getMessage())

    def test_wanted_file_none_file_path(self):
        """Test for unexpected wanted file path."""
        self.assertTrue(sync_drive.wanted_file(filters=None, ignore=None, file_path=__file__))
        self.assertFalse(sync_drive.wanted_file(filters=self.filters["file_extensions"], ignore=None, file_path=None))

    def test_wanted_file_empty_file_extensions(self):
        """Test for empty file extensions in wanted file."""
        original_filters = dict(self.filters)
        self.filters["file_extensions"] = []
        self.assertTrue(
            sync_drive.wanted_file(filters=self.filters["file_extensions"], ignore=None, file_path=__file__),
        )
        self.filters = dict(original_filters)

    def test_wanted_file_case_variations_extensions(self):
        """Test for wanted file extensions case variations."""
        self.filters["file_extensions"] = ["pY"]
        self.assertTrue(
            sync_drive.wanted_file(filters=self.filters["file_extensions"], ignore=None, file_path=__file__),
        )
        self.filters["file_extensions"] = ["pY"]
        self.assertTrue(
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"],
                ignore=None,
                file_path=os.path.join(os.path.dirname(__file__), "file.Py"),
            ),
        )

    def test_wanted_file_ignore(self):
        """Test for wanted file exclude regex."""
        self.ignore = ["*.md", ".git/"]
        self.assertFalse(
            sync_drive.wanted_file(
                filters=None,
                ignore=self.ignore,
                file_path=os.path.join(self.root, "/dir1/README.md"),
            ),
        )
        self.assertFalse(
            sync_drive.wanted_file(
                filters=None,
                ignore=self.ignore,
                file_path=os.path.join(self.root, "/.git/index"),
            ),
        )
        self.assertTrue(
            sync_drive.wanted_file(
                filters=None,
                ignore=self.ignore,
                file_path=os.path.join(os.path.dirname(__file__), "/dir1/index.html"),
            ),
        )

    def test_wanted_file_ignore_takes_precedences_over_filters(self):
        """Test for wanted folder exclude regex."""
        self.ignore = ["*.py"]
        self.filters["file_extensions"] = ["py"]
        self.assertFalse(
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"],
                ignore=self.ignore,
                file_path=os.path.join(self.root, "/dir1/index.py"),
            ),
        )

    def test_process_folder_wanted(self):
        """Test for valid wanted folder."""
        actual = sync_drive.process_folder(
            item=self.drive[self.items[0]],
            destination_path=self.destination_path,
            filters=self.filters["folders"],
            ignore=None,
            root=self.root,
        )
        self.assertIsNotNone(actual)
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))

    def test_process_folder_unwanted(self):
        """Test for valid unwanted folder."""
        actual = sync_drive.process_folder(
            item=self.drive[self.items[1]],
            destination_path=self.destination_path,
            filters=self.filters,
            ignore=None,
            root=self.root,
        )
        self.assertIsNone(actual)

    def test_process_folder_none_item(self):
        """Test for process folder item as None."""
        self.assertIsNone(
            sync_drive.process_folder(
                item=None,
                destination_path=self.destination_path,
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
            ),
        )

    def test_process_folder_none_destination_path(self):
        """Test for process folder destination path as None."""
        self.assertIsNone(
            sync_drive.process_folder(
                item=self.drive[self.items[1]],
                destination_path=None,
                filters=self.filters["folders"],
                ignore=None,
                root=self.root,
            ),
        )

    def test_process_folder_none_root(self):
        """Test for process folder root as None."""
        self.assertIsNone(
            sync_drive.process_folder(
                item=self.drive[self.items[1]],
                destination_path=self.destination_path,
                filters=self.filters["folders"],
                ignore=None,
                root=None,
            ),
        )

    def test_file_non_existing_file(self):
        """Test for file does not exist."""
        self.assertFalse(sync_drive.file_exists(item=self.file_item, local_file=self.local_file_path))

    def test_file_existing_file(self):
        """Test for file exists."""
        sync_drive.download_file(item=self.file_item, local_file=self.local_file_path)
        actual = sync_drive.file_exists(item=self.file_item, local_file=self.local_file_path)
        self.assertTrue(actual)
        # Verbose
        sync_drive.download_file(item=self.file_item, local_file=self.local_file_path)
        with self.assertLogs(logger=LOGGER, level="DEBUG") as captured:
            actual = sync_drive.file_exists(item=self.file_item, local_file=self.local_file_path)
            self.assertTrue(actual)
            self.assertTrue(len(captured.records) > 0)
            self.assertIn("No changes detected.", captured.records[0].getMessage())

    def test_file_exists_none_item(self):
        """Test if item is None."""
        self.assertFalse(sync_drive.file_exists(item=None, local_file=self.local_file_path))

    def test_file_exists_none_local_file(self):
        """Test if local_file is None."""
        self.assertFalse(sync_drive.file_exists(item=self.file_item, local_file=None))

    def test_download_file(self):
        """Test for valid file download."""
        self.assertTrue(sync_drive.download_file(item=self.file_item, local_file=self.local_file_path))

        # Verbose
        with self.assertLogs() as captured:
            self.assertTrue(sync_drive.download_file(item=self.file_item, local_file=self.local_file_path))
            self.assertTrue(len(captured.records) > 0)
            self.assertIn("Downloading ", captured.records[0].getMessage())

    def test_download_file_none_item(self):
        """Test for item as None."""
        self.assertFalse(sync_drive.download_file(item=None, local_file=self.local_file_path))

    def test_download_file_none_local_file(self):
        """Test for local_file as None."""
        self.assertFalse(sync_drive.download_file(item=self.file_item, local_file=None))

    def test_download_file_non_existing(self):
        """Test for non-existent local file download."""
        self.assertFalse(
            sync_drive.download_file(
                item=self.file_item,
                local_file=os.path.join(self.destination_path, "non-existent-folder", self.file_name),
            ),
        )

    def test_download_file_key_error_data_token(self):
        """Test for data token key error."""
        with patch.object(self.file_item, "open") as mock_item:
            mock_item.side_effect = KeyError("data_token")
            self.assertFalse(sync_drive.download_file(item=self.file_item, local_file=self.local_file_path))

    def test_process_file_non_existing(self):
        """Test for non-existing file."""
        files = set()
        # file does not exist
        self.assertTrue(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=files,
            ),
        )
        self.assertTrue(len(files) == 1)

    def test_process_file_existing(self):
        """Test for existing file."""
        files = set()
        sync_drive.process_file(
            item=self.file_item,
            destination_path=self.destination_path,
            filters=self.filters["file_extensions"],
            ignore=None,
            files=files,
        )
        # file already exists but not changed
        self.assertFalse(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=files,
            ),
        )

    def test_process_file_not_wanted(self):
        """Test for unwanted file."""
        files = set()
        self.assertFalse(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters,
                ignore=None,
                files=files,
            ),
        )

    def test_process_file_none_item(self):
        """Test for file item as None."""
        files = set()
        self.assertFalse(
            sync_drive.process_file(
                item=None,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=files,
            ),
        )

    def test_process_file_none_destination_path(self):
        """Test for destination path as None."""
        files = set()
        self.assertFalse(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=None,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=files,
            ),
        )

    def test_process_file_none_filters(self):
        """Test for filters as None."""
        files = set()
        self.assertTrue(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=None,
                ignore=None,
                files=files,
            ),
        )

    def test_process_file_none_files(self):
        """Test for files as None."""
        self.assertFalse(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=None,
            ),
        )

    def test_process_file_existing_file(self):
        """Test for existing file."""
        files = set()
        # Existing file
        sync_drive.download_file(item=self.file_item, local_file=self.local_file_path)
        self.assertFalse(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=files,
            ),
        )
        # Locally modified file
        shutil.copyfile(
            os.path.join(tests.DATA_DIR, "thumb.jpeg"),
            os.path.join(self.destination_path, self.file_item.name),
        )
        self.assertTrue(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=files,
            ),
        )

    def test_remove_obsolete_file(self):
        """Test for removing obsolete file."""
        obsolete_path = os.path.join(self.destination_path, "obsolete")
        os.mkdir(obsolete_path)
        obsolete_file_path = os.path.join(obsolete_path, os.path.basename(__file__))
        shutil.copyfile(__file__, obsolete_file_path)
        # Remove the file
        files = set()
        files.add(obsolete_path)
        actual = sync_drive.remove_obsolete(destination_path=self.destination_path, files=files)
        self.assertTrue(len(actual) == 1)
        self.assertFalse(os.path.isfile(obsolete_file_path))

    def test_remove_obsolete_directory(self):
        """Test for removing obsolete directory."""
        files = set()
        obsolete_path = os.path.join(self.destination_path, "obsolete")
        os.mkdir(obsolete_path)
        obsolete_file_path = os.path.join(obsolete_path, os.path.basename(__file__))
        shutil.copyfile(__file__, obsolete_file_path)
        files.add(obsolete_path)
        shutil.copyfile(__file__, obsolete_file_path)
        # Remove the directory
        files.remove(obsolete_path)
        actual = sync_drive.remove_obsolete(destination_path=self.destination_path, files=files)
        self.assertTrue(len(actual) == 1)
        self.assertFalse(os.path.isdir(obsolete_path))
        # Remove the directory with file
        os.mkdir(obsolete_path)
        shutil.copyfile(__file__, obsolete_file_path)
        actual = sync_drive.remove_obsolete(destination_path=self.destination_path, files=files)
        self.assertTrue(len(actual) > 0)
        self.assertFalse(os.path.isdir(obsolete_path))
        self.assertFalse(os.path.isfile(obsolete_file_path))
        # Verbose
        with self.assertLogs() as captured:
            os.mkdir(obsolete_path)
            shutil.copyfile(__file__, obsolete_file_path)
            actual = sync_drive.remove_obsolete(destination_path=self.destination_path, files=files)
            self.assertTrue(len(actual) > 0)
            self.assertFalse(os.path.isdir(obsolete_path))
            self.assertFalse(os.path.isfile(obsolete_file_path))
            self.assertTrue(len(captured.records) > 0)
            self.assertIn("Removing ", captured.records[0].getMessage())

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_remove_obsolete_package(self, mock_read_config, mock_service, mock_get_username, mock_get_password):
        """Test for removing obsolete package."""
        mock_service = self.service
        config = self.config.copy()
        config["drive"]["remove_obsolete"] = True
        config["drive"]["destination"] = self.destination_path
        mock_read_config.return_value = config
        ms_band_package_local_path = os.path.join(self.destination_path, "Obsidian", "Sample", "ms.band")
        files = sync_drive.sync_drive(config=config, drive=mock_service.drive)
        self.assertIsNotNone(files)
        files.remove(ms_band_package_local_path)
        files = sync_drive.remove_obsolete(destination_path=self.destination_path, files=files)
        self.assertFalse(os.path.exists(ms_band_package_local_path))

    def test_remove_obsolete_none_destination_path(self):
        """Test for destination path as None."""
        self.assertTrue(len(sync_drive.remove_obsolete(destination_path=None, files=set())) == 0)

    def test_remove_obsolete_none_files(self):
        """Test for files as None."""
        obsolete_path = os.path.join(self.destination_path, "obsolete")
        self.assertTrue(len(sync_drive.remove_obsolete(destination_path=obsolete_path, files=None)) == 0)

    def test_sync_directory_without_remove(self):
        """Test for remove as False."""
        actual = sync_drive.sync_directory(
            drive=self.drive,
            destination_path=self.destination_path,
            root=self.root,
            items=self.drive.dir(),
            top=True,
            filters=self.filters,
            remove=False,
        )
        self.assertTrue(len(actual) == 49)
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy")))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy", "Test")))
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, "icloudpy", "Test", "Document scanne 2.pdf")),
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, "icloudpy", "Test", "Scanned document 1.pdf")),
        )

    def test_sync_directory_with_remove(self):
        """Test for remove as True."""
        os.mkdir(os.path.join(self.destination_path, "obsolete"))
        shutil.copyfile(__file__, os.path.join(self.destination_path, "obsolete", "obsolete.py"))
        actual = sync_drive.sync_directory(
            drive=self.drive,
            destination_path=self.destination_path,
            root=self.root,
            items=self.drive.dir(),
            top=True,
            filters=self.filters,
            ignore=self.ignore,
            remove=True,
        )
        self.assertTrue(len(actual) == 49)
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy")))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy", "Test")))
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, "icloudpy", "Test", "Document scanne 2.pdf")),
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, "icloudpy", "Test", "Scanned document 1.pdf")),
        )

    def test_sync_directory_without_folder_filter(self):
        """Test for no folder filter."""
        original_filters = dict(self.filters)
        del self.filters["folders"]
        actual = sync_drive.sync_directory(
            drive=self.drive,
            destination_path=self.destination_path,
            root=self.root,
            items=self.drive.dir(),
            top=True,
            filters=self.filters,
            ignore=self.ignore,
            remove=False,
        )
        self.assertTrue(len(actual) == 53)
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy")))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy", "Test")))
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, "icloudpy", "Test", "Document scanne 2.pdf")),
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, "icloudpy", "Test", "Scanned document 1.pdf")),
        )
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "unwanted")))

        self.filters = dict(original_filters)

    def test_sync_directory_none_drive(self):
        """Test for drive as None."""
        self.assertTrue(
            len(
                sync_drive.sync_directory(
                    drive=None,
                    destination_path=self.destination_path,
                    root=self.root,
                    items=self.drive.dir(),
                    top=True,
                    filters=self.filters,
                    ignore=self.ignore,
                    remove=False,
                ),
            )
            == 0,
        )

    def test_sync_directory_none_destination(self):
        """Test for destination as None."""
        self.assertTrue(
            len(
                sync_drive.sync_directory(
                    drive=self.drive,
                    destination_path=None,
                    root=self.root,
                    items=self.drive.dir(),
                    top=True,
                    filters=self.filters,
                    ignore=self.ignore,
                    remove=False,
                ),
            )
            == 0,
        )

    def test_sync_directory_none_root(self):
        """Test for root as None."""
        self.assertTrue(
            len(
                sync_drive.sync_directory(
                    drive=self.drive,
                    destination_path=self.destination_path,
                    root=None,
                    items=self.drive.dir(),
                    top=True,
                    filters=self.filters,
                    ignore=self.ignore,
                    remove=False,
                ),
            )
            == 0,
        )

    def test_sync_directory_none_items(self):
        """Test for items as None."""
        self.assertTrue(
            len(
                sync_drive.sync_directory(
                    drive=self.drive,
                    destination_path=self.destination_path,
                    root=self.root,
                    items=None,
                    top=True,
                    filters=self.filters,
                    ignore=self.ignore,
                    remove=False,
                ),
            )
            == 0,
        )

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_drive_valids(self, mock_read_config, mock_service, mock_get_username, mock_get_password):
        """Test for valid sync_drive."""
        mock_service = self.service
        config = self.config.copy()
        config["drive"]["destination"] = self.destination_path
        mock_read_config.return_value = config
        self.assertIsNotNone(sync_drive.sync_drive(config=config, drive=mock_service.drive))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy")))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy", "Test")))
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, "icloudpy", "Test", "Document scanne 2.pdf")),
        )
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, "icloudpy", "Test", "Scanned document 1.pdf")),
        )
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "Obsidian")))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "Obsidian", "Sample")))
        self.assertTrue(os.path.isfile(os.path.join(self.destination_path, "Obsidian", "Sample", "This is a title.md")))
        self.assertEqual(
            sum(
                f.stat().st_size
                for f in Path(os.path.join(self.destination_path, "Obsidian", "Sample", "Project.band")).glob("**/*")
                if f.is_file()
            ),
            sum(
                f.stat().st_size
                for f in Path(os.path.join(tests.DATA_DIR, "Project_original.band")).glob("**/*")
                if f.is_file()
            ),
        )

    def test_process_file_special_chars_package(self):
        """Test for special characters package."""
        files = set()
        # Download the package
        self.assertTrue(
            sync_drive.process_file(
                item=self.special_chars_package_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=files,
            ),
        )

    def test_process_file_existing_package(self):
        """Test for existing package."""
        files = set()
        # Existing package
        sync_drive.download_file(item=self.package_item, local_file=self.local_package_path)
        # Do not download the package
        self.assertFalse(
            sync_drive.process_file(
                item=self.package_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=files,
            ),
        )
        # Modify local package
        shutil.copyfile(
            os.path.join(tests.DATA_DIR, "thumb.jpeg"),
            os.path.join(self.local_package_path, self.file_item.name),
        )
        # Download the package
        self.assertTrue(
            sync_drive.process_file(
                item=self.package_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=files,
            ),
        )

    def test_process_file_nested_package_extraction(self):
        """Test for nested package extraction."""
        files = set()
        self.assertTrue(
            sync_drive.process_file(
                item=self.package_item_nested,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                ignore=None,
                files=files,
            ),
        )
        self.assertTrue(os.path.exists(os.path.join(self.destination_path, "ms.band")))

        self.assertEqual(
            sum(
                f.stat().st_size
                for f in Path(os.path.join(self.destination_path, "ms.band")).glob("**/*")
                if f.is_file()
            ),
            sum(f.stat().st_size for f in Path(os.path.join(tests.DATA_DIR, "ms.band")).glob("**/*") if f.is_file()),
        )

    def test_process_package_invalid_package_type(self):
        """Test for invalid package type."""
        self.assertFalse(sync_drive.process_package(local_file=os.path.join(DATA_DIR, "medium.jpeg")))

    def test_execution_continuation_on_icloudpy_exception(self):
        """Test for icloudpy exception."""
        with patch.object(self.file_item, "open") as mocked_file_method, patch.object(
            self.folder_item, "dir",
        ) as mocked_folder_method:
            mocked_file_method.side_effect = mocked_folder_method.side_effect = ICloudPyAPIResponseException(
                "Exception occurred.",
            )
            filters = dict(self.filters)
            filters["folders"].append("unwanted")
            actual = sync_drive.sync_directory(
                drive=self.drive,
                destination_path=self.destination_path,
                root=self.root,
                items=self.drive.dir(),
                top=True,
                filters=filters,
                ignore=self.ignore,
                remove=False,
            )
            self.assertTrue(len(actual) == 50)
            self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy")))
            self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy", "Test")))
            self.assertTrue(
                os.path.isfile(
                    os.path.join(
                        self.destination_path,
                        "icloudpy",
                        "Test",
                        "Document scanne 2.pdf",
                    ),
                ),
            )
            self.assertFalse(
                os.path.isfile(
                    os.path.join(
                        self.destination_path,
                        "icloudpy",
                        "Test",
                        "Scanned document 1.pdf",
                    ),
                ),
            )

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER)
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_child_ignored_folder(self, mock_read_config, mock_service, mock_get_username, mock_get_password):
        """Test for child ignored folder."""
        mock_service = self.service
        config = self.config.copy()
        config["drive"]["destination"] = self.destination_path
        config["drive"]["ignore"] = ["icloudpy/*"]
        mock_read_config.return_value = config
        self.assertIsNotNone(sync_drive.sync_drive(config=config, drive=mock_service.drive))
        self.assertFalse(os.path.exists(os.path.join(self.destination_path, "icloudpy", "Test")))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "Obsidian")))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "Obsidian", "Sample")))
        self.assertTrue(os.path.isfile(os.path.join(self.destination_path, "Obsidian", "Sample", "This is a title.md")))
        self.assertEqual(
            sum(
                f.stat().st_size
                for f in Path(os.path.join(self.destination_path, "Obsidian", "Sample", "Project.band")).glob("**/*")
                if f.is_file()
            ),
            sum(
                f.stat().st_size
                for f in Path(os.path.join(tests.DATA_DIR, "Project_original.band")).glob("**/*")
                if f.is_file()
            ),
        )
