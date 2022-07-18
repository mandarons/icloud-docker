__author__ = "Mandar Patil (mandarons@pm.me)"

import unittest
import os
import shutil
from unittest.mock import patch

import tests
from tests import data
from src import LOGGER, sync_drive, read_config


class TestSyncDrive(unittest.TestCase):
    def setUp(self) -> None:
        self.config = read_config(config_path=tests.CONFIG_PATH)
        self.filters = self.config["drive"]["filters"]
        self.root = tests.DRIVE_DIR
        self.destination_path = self.root
        os.makedirs(self.destination_path, exist_ok=True)
        self.service = data.ICloudPyServiceMock(
            data.AUTHENTICATED_USER, data.VALID_PASSWORD
        )
        self.drive = self.service.drive
        self.items = self.drive.dir()
        self.file_item = self.drive[self.items[4]]["Test"]["Scanned document 1.pdf"]
        self.package_item = self.drive[self.items[6]]["Sample"]["Project.band"]
        self.file_name = "Scanned document 1.pdf"
        self.package_name = "Project.band"
        self.local_file_path = os.path.join(self.destination_path, self.file_name)
        self.local_package_path = os.path.join(self.destination_path, self.package_name)

    def tearDown(self) -> None:
        shutil.rmtree(tests.TEMP_DIR)

    def test_wanted_parent_folder_none_filters(self):
        self.filters["folders"] = ["dir1/dir11"]
        self.assertTrue(
            sync_drive.wanted_parent_folder(
                filters=None,
                root=self.root,
                folder_path=os.path.join(self.root, "dir1/dir11"),
            )
        )

    def test_wanted_parent_folder(self):
        self.filters["folders"] = ["dir1/dir11"]
        self.assertTrue(
            sync_drive.wanted_parent_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1/dir11/some/dirs/file.ext"),
            )
        )

    def test_wanted_parent_folder_missing_parent_folder(self):
        self.filters["folders"] = ["dir1/dir11"]
        self.assertFalse(
            sync_drive.wanted_parent_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            )
        )

    def test_wanted_folder_single_variations(self):
        self.filters["folders"] = ["dir1"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            )
        )
        self.filters["folders"] = ["/dir1"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            )
        )
        self.filters["folders"] = ["dir1/"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            )
        )
        self.filters["folders"] = ["/dir1/"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            )
        )

    def test_wanted_folder_single_path(self):
        self.filters["folders"] = ["dir1/dir2/dir3/", "dir1//dir2/dir3//"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            )
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2"),
            )
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2", "dir3"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir3"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir2"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir3"),
            )
        )
        self.filters["folders"] = ["dir1//dir2/dir3//"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            )
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2"),
            )
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2", "dir3"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir3"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir2"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir3"),
            )
        )

    def test_wanted_folder_multiple(self):
        self.filters["folders"] = ["dir1", "dir2"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            )
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir2"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir3"),
            )
        )

    def test_wanted_folder_multiple_paths(self):
        self.filters["folders"] = ["dir1/dir2/dir3/", "dirA/dirB/dirC"]
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            )
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2"),
            )
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir2", "dir3"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1", "dir3"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir2"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir3"),
            )
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dirA"),
            )
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dirA", "dirB"),
            )
        )
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dirA", "dirB", "dirC"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dirA", "dirC"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dirB"),
            )
        )
        self.assertFalse(
            sync_drive.wanted_folder(
                filters=self.filters,
                root=self.root,
                folder_path=os.path.join(self.root, "dirC"),
            )
        )

    def test_wanted_folder_empty(self):
        original_filters = dict(self.filters)
        self.filters["folders"] = []
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"],
                root=self.root,
                folder_path=os.path.join(self.root, "dir1"),
            )
        )
        self.filters = dict(original_filters)

    def test_wanted_folder_none_folder_path(self):
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"], root=self.root, folder_path=None
            )
        )

    def test_wanted_folder_none_filters(self):
        self.assertTrue(
            sync_drive.wanted_folder(filters=None, root=self.root, folder_path="dir1")
        )

    def test_wanted_folder_none_root(self):
        self.assertTrue(
            sync_drive.wanted_folder(
                filters=self.filters["folders"], root=None, folder_path="dir1"
            )
        )

    def test_wanted_file(self):
        self.filters["file_extensions"] = ["py"]
        self.assertTrue(
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"], file_path=__file__
            )
        )

    def test_wanted_file_missing(self):
        self.assertFalse(
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"], file_path=tests.CONFIG_PATH
            )
        )

    def test_wanted_file_check_log(self):
        with self.assertLogs(logger=LOGGER, level="DEBUG") as captured:
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"], file_path=tests.CONFIG_PATH
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIn(
                "Skipping the unwanted file", captured.records[0].getMessage()
            )

    def test_wanted_file_none_file_path(self):
        self.assertTrue(sync_drive.wanted_file(filters=None, file_path=__file__))
        self.assertFalse(
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"], file_path=None
            )
        )

    def test_wanted_file_empty_file_extensions(self):
        original_filters = dict(self.filters)
        self.filters["file_extensions"] = []
        self.assertTrue(
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"], file_path=__file__
            )
        )
        self.filters = dict(original_filters)

    def test_wanted_file_case_variations_extensions(self):
        self.filters["file_extensions"] = ["pY"]
        self.assertTrue(
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"], file_path=__file__
            )
        )
        self.filters["file_extensions"] = ["pY"]
        self.assertTrue(
            sync_drive.wanted_file(
                filters=self.filters["file_extensions"],
                file_path=os.path.join(os.path.dirname(__file__), "file.Py"),
            )
        )

    def test_process_folder_wanted(self):
        # Wanted folder
        actual = sync_drive.process_folder(
            item=self.drive[self.items[0]],
            destination_path=self.destination_path,
            filters=self.filters["folders"],
            root=self.root,
        )
        self.assertIsNotNone(actual)
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))

    def test_process_folder_unwanted(self):

        # Unwanted folder
        actual = sync_drive.process_folder(
            item=self.drive[self.items[1]],
            destination_path=self.destination_path,
            filters=self.filters,
            root=self.root,
        )
        self.assertIsNone(actual)

    def test_process_folder_none_item(self):
        self.assertIsNone(
            sync_drive.process_folder(
                item=None,
                destination_path=self.destination_path,
                filters=self.filters["folders"],
                root=self.root,
            )
        )

    def test_process_folder_none_destination_path(self):
        self.assertIsNone(
            sync_drive.process_folder(
                item=self.drive[self.items[1]],
                destination_path=None,
                filters=self.filters["folders"],
                root=self.root,
            )
        )

    def test_process_folder_none_root(self):
        self.assertIsNone(
            sync_drive.process_folder(
                item=self.drive[self.items[1]],
                destination_path=self.destination_path,
                filters=self.filters["folders"],
                root=None,
            )
        )

    def test_file_non_existing_file(self):
        # File does not exist
        self.assertFalse(
            sync_drive.file_exists(item=self.file_item, local_file=self.local_file_path)
        )

    def test_file_existing_file(self):
        # File exists
        sync_drive.download_file(item=self.file_item, local_file=self.local_file_path)
        actual = sync_drive.file_exists(
            item=self.file_item, local_file=self.local_file_path
        )
        self.assertTrue(actual)
        # Verbose
        sync_drive.download_file(item=self.file_item, local_file=self.local_file_path)
        with self.assertLogs(logger=LOGGER, level="DEBUG") as captured:
            actual = sync_drive.file_exists(
                item=self.file_item, local_file=self.local_file_path
            )
            self.assertTrue(actual)
            self.assertTrue(len(captured.records) > 0)
            self.assertIn("No changes detected.", captured.records[0].getMessage())

    def test_file_exists_none_item(self):
        self.assertFalse(
            sync_drive.file_exists(item=None, local_file=self.local_file_path)
        )

    def test_file_exists_none_local_file(self):
        self.assertFalse(sync_drive.file_exists(item=self.file_item, local_file=None))

    def test_download_file(self):
        self.assertTrue(
            sync_drive.download_file(
                item=self.file_item, local_file=self.local_file_path
            )
        )

        # Verbose
        with self.assertLogs() as captured:
            self.assertTrue(
                sync_drive.download_file(
                    item=self.file_item, local_file=self.local_file_path
                )
            )
            self.assertTrue(len(captured.records) > 0)
            self.assertIn("Downloading ", captured.records[0].getMessage())

    def test_download_file_none_item(self):
        self.assertFalse(
            sync_drive.download_file(item=None, local_file=self.local_file_path)
        )

    def test_download_file_none_local_file(self):
        self.assertFalse(sync_drive.download_file(item=self.file_item, local_file=None))

    def test_download_file_non_existing(self):
        self.assertFalse(
            sync_drive.download_file(
                item=self.file_item,
                local_file=os.path.join(
                    self.destination_path, "non-existent-folder", self.file_name
                ),
            )
        )

    def test_download_file_key_error_data_token(self):
        with patch.object(self.file_item, "open") as mock_item:
            mock_item.side_effect = KeyError("data_token")
            self.assertFalse(
                sync_drive.download_file(
                    item=self.file_item, local_file=self.local_file_path
                )
            )

    def test_process_file_non_existing(self):
        files = set()
        # file does not exist
        self.assertTrue(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                files=files,
            )
        )
        self.assertTrue(len(files) == 1)

    def test_process_file_existing(self):
        files = set()
        sync_drive.process_file(
            item=self.file_item,
            destination_path=self.destination_path,
            filters=self.filters["file_extensions"],
            files=files,
        )
        # file already exists but not changed
        self.assertFalse(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                files=files,
            )
        )

    def test_process_file_not_wanted(self):
        files = set()
        self.assertFalse(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters,
                files=files,
            )
        )

    def test_process_file_none_item(self):
        files = set()
        self.assertFalse(
            sync_drive.process_file(
                item=None,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                files=files,
            )
        )

    def test_process_file_none_destination_path(self):
        files = set()
        self.assertFalse(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=None,
                filters=self.filters["file_extensions"],
                files=files,
            )
        )

    def test_process_file_none_filters(self):
        files = set()
        self.assertTrue(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=None,
                files=files,
            )
        )

    def test_process_file_none_files(self):
        self.assertFalse(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                files=None,
            )
        )

    def test_process_file_existing_file(self):
        files = set()
        # Existing file
        sync_drive.download_file(item=self.file_item, local_file=self.local_file_path)
        self.assertFalse(
            sync_drive.process_file(
                item=self.file_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                files=files,
            )
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
                files=files,
            )
        )

    def test_remove_obsolete_file(self):
        obsolete_path = os.path.join(self.destination_path, "obsolete")
        os.mkdir(obsolete_path)
        obsolete_file_path = os.path.join(obsolete_path, os.path.basename(__file__))
        shutil.copyfile(__file__, obsolete_file_path)
        # Remove the file
        files = set()
        files.add(obsolete_path)
        actual = sync_drive.remove_obsolete(
            destination_path=self.destination_path, files=files
        )
        self.assertTrue(len(actual) == 1)
        self.assertFalse(os.path.isfile(obsolete_file_path))

    def test_remove_obsolete_directory(self):
        files = set()
        obsolete_path = os.path.join(self.destination_path, "obsolete")
        os.mkdir(obsolete_path)
        obsolete_file_path = os.path.join(obsolete_path, os.path.basename(__file__))
        shutil.copyfile(__file__, obsolete_file_path)
        files.add(obsolete_path)
        shutil.copyfile(__file__, obsolete_file_path)
        # Remove the directory
        files.remove(obsolete_path)
        actual = sync_drive.remove_obsolete(
            destination_path=self.destination_path, files=files
        )
        self.assertTrue(len(actual) == 1)
        self.assertFalse(os.path.isdir(obsolete_path))
        # Remove the directory with file
        os.mkdir(obsolete_path)
        shutil.copyfile(__file__, obsolete_file_path)
        actual = sync_drive.remove_obsolete(
            destination_path=self.destination_path, files=files
        )
        self.assertTrue(len(actual) > 0)
        self.assertFalse(os.path.isdir(obsolete_path))
        self.assertFalse(os.path.isfile(obsolete_file_path))
        # Verbose
        with self.assertLogs() as captured:
            os.mkdir(obsolete_path)
            shutil.copyfile(__file__, obsolete_file_path)
            actual = sync_drive.remove_obsolete(
                destination_path=self.destination_path, files=files
            )
            self.assertTrue(len(actual) > 0)
            self.assertFalse(os.path.isdir(obsolete_path))
            self.assertFalse(os.path.isfile(obsolete_file_path))
            self.assertTrue(len(captured.records) > 0)
            self.assertIn("Removing ", captured.records[0].getMessage())

    def test_remove_obsolete_none_destination_path(self):
        self.assertTrue(
            len(sync_drive.remove_obsolete(destination_path=None, files=set())) == 0
        )

    def test_remove_obsolete_none_files(self):
        obsolete_path = os.path.join(self.destination_path, "obsolete")
        self.assertTrue(
            len(sync_drive.remove_obsolete(destination_path=obsolete_path, files=None))
            == 0
        )

    def test_sync_directory_without_remove(self):
        actual = sync_drive.sync_directory(
            drive=self.drive,
            destination_path=self.destination_path,
            root=self.root,
            items=self.drive.dir(),
            top=True,
            filters=self.filters,
            remove=False,
        )
        self.assertTrue(len(actual) == 9)
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy")))
        self.assertTrue(
            os.path.isdir(os.path.join(self.destination_path, "icloudpy", "Test"))
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.destination_path, "icloudpy", "Test", "Document scanne 2.pdf"
                )
            )
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.destination_path, "icloudpy", "Test", "Scanned document 1.pdf"
                )
            )
        )

    def test_sync_directory_with_remove(self):
        os.mkdir(os.path.join(self.destination_path, "obsolete"))
        shutil.copyfile(
            __file__, os.path.join(self.destination_path, "obsolete", "obsolete.py")
        )
        actual = sync_drive.sync_directory(
            drive=self.drive,
            destination_path=self.destination_path,
            root=self.root,
            items=self.drive.dir(),
            top=True,
            filters=self.filters,
            remove=True,
        )
        self.assertTrue(len(actual) == 9)
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy")))
        self.assertTrue(
            os.path.isdir(os.path.join(self.destination_path, "icloudpy", "Test"))
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.destination_path, "icloudpy", "Test", "Document scanne 2.pdf"
                )
            )
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.destination_path, "icloudpy", "Test", "Scanned document 1.pdf"
                )
            )
        )

    def test_sync_directory_without_folder_filter(self):
        original_filters = dict(self.filters)
        del self.filters["folders"]
        actual = sync_drive.sync_directory(
            drive=self.drive,
            destination_path=self.destination_path,
            root=self.root,
            items=self.drive.dir(),
            top=True,
            filters=self.filters,
            remove=False,
        )
        self.assertTrue(len(actual) == 13)
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy")))
        self.assertTrue(
            os.path.isdir(os.path.join(self.destination_path, "icloudpy", "Test"))
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.destination_path, "icloudpy", "Test", "Document scanne 2.pdf"
                )
            )
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.destination_path, "icloudpy", "Test", "Scanned document 1.pdf"
                )
            )
        )
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "unwanted")))

        self.filters = dict(original_filters)

    def test_sync_directory_none_drive(self):
        self.assertTrue(
            0
            == len(
                sync_drive.sync_directory(
                    drive=None,
                    destination_path=self.destination_path,
                    root=self.root,
                    items=self.drive.dir(),
                    top=True,
                    filters=self.filters,
                    remove=False,
                )
            )
        )

    def test_sync_directory_none_destination(self):
        self.assertTrue(
            0
            == len(
                sync_drive.sync_directory(
                    drive=self.drive,
                    destination_path=None,
                    root=self.root,
                    items=self.drive.dir(),
                    top=True,
                    filters=self.filters,
                    remove=False,
                )
            )
        )

    def test_sync_directory_none_root(self):
        self.assertTrue(
            0
            == len(
                sync_drive.sync_directory(
                    drive=self.drive,
                    destination_path=self.destination_path,
                    root=None,
                    items=self.drive.dir(),
                    top=True,
                    filters=self.filters,
                    remove=False,
                )
            )
        )

    def test_sync_directory_none_items(self):
        self.assertTrue(
            0
            == len(
                sync_drive.sync_directory(
                    drive=self.drive,
                    destination_path=self.destination_path,
                    root=self.root,
                    items=None,
                    top=True,
                    filters=self.filters,
                    remove=False,
                )
            )
        )

    @patch(target="keyring.get_password", return_value=data.VALID_PASSWORD)
    @patch(
        target="src.config_parser.get_username", return_value=data.AUTHENTICATED_USER
    )
    @patch("icloudpy.ICloudPyService")
    @patch("src.read_config")
    def test_sync_drive_valids(
        self, mock_read_config, mock_service, mock_get_username, mock_get_password
    ):
        mock_service = self.service
        config = self.config.copy()
        config["drive"]["destination"] = self.destination_path
        mock_read_config.return_value = config
        self.assertIsNotNone(
            sync_drive.sync_drive(config=config, drive=mock_service.drive)
        )
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "icloudpy")))
        self.assertTrue(
            os.path.isdir(os.path.join(self.destination_path, "icloudpy", "Test"))
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.destination_path, "icloudpy", "Test", "Document scanne 2.pdf"
                )
            )
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.destination_path, "icloudpy", "Test", "Scanned document 1.pdf"
                )
            )
        )
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, "Obsidian")))
        self.assertTrue(
            os.path.isdir(os.path.join(self.destination_path, "Obsidian", "Sample"))
        )
        self.assertTrue(
            os.path.isfile(
                os.path.join(
                    self.destination_path, "Obsidian", "Sample", "This is a title.md"
                )
            )
        )
        self.assertEqual(
            sum(
                os.path.getsize(f)
                for f in os.listdir(
                    os.path.join(
                        self.destination_path, "Obsidian", "Sample", "Project.band"
                    )
                )
                if os.path.isfile(f)
            ),
            sum(
                os.path.getsize(f)
                for f in os.listdir(
                    os.path.join(tests.DATA_DIR, "Project_original.band")
                )
                if os.path.isfile(f)
            ),
        )

    def test_process_file_existing_package(self):
        files = set()
        # Existing package
        sync_drive.download_file(
            item=self.package_item, local_file=self.local_package_path
        )
        # Do not download the package
        self.assertFalse(
            sync_drive.process_file(
                item=self.package_item,
                destination_path=self.destination_path,
                filters=self.filters["file_extensions"],
                files=files,
            )
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
                files=files,
            )
        )
