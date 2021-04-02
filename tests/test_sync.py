__author__ = 'Mandar Patil (mandarons@pm.me)'

import unittest
import os
import shutil
from unittest.mock import patch

import tests
from tests import data
from src import sync, config_parser


class TestSync(unittest.TestCase):

    def setUp(self) -> None:
        self.config = config_parser.read_config(config_path=tests.CONFIG_PATH)
        self.filters = self.config['filters']
        self.root = tests.DRIVE_DIR
        self.destination_path = self.root
        os.makedirs(self.destination_path, exist_ok=True)
        self.service = data.PyiCloudServiceMock(data.AUTHENTICATED_USER, data.VALID_PASSWORD)
        self.drive = self.service.drive
        self.items = self.drive.dir()
        self.file_item = self.drive[self.items[4]]['Test']['Scanned document 1.pdf']
        self.file_name = 'Scanned document 1.pdf'
        self.local_file_path = os.path.join(self.destination_path, self.file_name)

    def tearDown(self) -> None:
        shutil.rmtree(tests.TEMP_DIR)

    def test_wanted_folder_single(self):
        self.filters['folders'] = ['dir1']
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1')))
        self.filters['folders'] = ['/dir1']
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1')))
        self.filters['folders'] = ['dir1/']
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1')))
        self.filters['folders'] = ['/dir1/']
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1')))

    def test_wanted_folder_single_path(self):
        self.filters['folders'] = ['dir1/dir2/dir3/', 'dir1//dir2/dir3//']
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1')))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1', 'dir2')))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1', 'dir2', 'dir3')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dir1', 'dir3')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dir2')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dir3')))
        self.filters['folders'] = ['dir1//dir2/dir3//']
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1')))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1', 'dir2')))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1', 'dir2', 'dir3')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dir1', 'dir3')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dir2')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dir3')))

    def test_wanted_folder_multiple(self):
        self.filters['folders'] = ['dir1', 'dir2']
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1')))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir2')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dir3')))

    def test_wanted_folder_multiple_paths(self):
        self.filters['folders'] = ['dir1/dir2/dir3/', 'dirA/dirB/dirC']
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1')))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1', 'dir2')))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1', 'dir2', 'dir3')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dir1', 'dir3')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dir2')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dir3')))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dirA')))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dirA', 'dirB')))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dirA', 'dirB', 'dirC')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dirA', 'dirC')))
        self.assertFalse(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                            folder_path=os.path.join(self.root, 'dirB')))
        self.assertFalse(sync.wanted_folder(filters=self.filters, root=self.root,
                                            folder_path=os.path.join(self.root, 'dirC')))

    def test_wanted_folder_empty(self):
        original_filters = dict(self.filters)
        self.filters['folders'] = []
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=os.path.join(self.root, 'dir1')))
        self.filters = dict(original_filters)

    def test_wanted_folder_invalids(self):
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=self.root,
                                           folder_path=None))
        self.assertTrue(sync.wanted_folder(filters=None, root=self.root,
                                           folder_path='dir1'))
        self.assertTrue(sync.wanted_folder(filters=self.filters['folders'], root=None,
                                           folder_path='dir1'))

    def test_wanted_file_valids(self):
        self.filters['file_extensions'] = ['py']
        self.assertTrue(sync.wanted_file(filters=self.filters['file_extensions'], file_path=__file__))
        self.assertFalse(sync.wanted_file(filters=self.filters['file_extensions'], file_path=tests.CONFIG_PATH))

    def test_wanted_file_invalids(self):
        original_filters = dict(self.filters)
        self.assertTrue(sync.wanted_file(filters=None, file_path=__file__))
        self.assertFalse(sync.wanted_file(filters=self.filters['file_extensions'], file_path=None))
        self.filters['file_extensions'] = []
        self.assertTrue(sync.wanted_file(filters=self.filters['file_extensions'], file_path=__file__))
        self.filters = dict(original_filters)
        self.filters['file_extensions'] = ['pY']
        self.assertTrue(sync.wanted_file(filters=self.filters['file_extensions'], file_path=__file__))
        self.filters['file_extensions'] = ['pY']
        self.assertTrue(
            sync.wanted_file(filters=self.filters['file_extensions'], file_path=os.path.join(os.path.dirname(__file__), 'file.Py')))

    def test_process_folder_valids(self):
        # Wanted folder
        actual = sync.process_folder(item=self.drive[self.items[0]], destination_path=self.destination_path,
                                     filters=self.filters['folders'], root=self.root)
        self.assertIsNotNone(actual)
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))

        # Unwanted folder
        actual = sync.process_folder(item=self.drive[self.items[1]], destination_path=self.destination_path,
                                     filters=self.filters, root=self.root)
        self.assertIsNone(actual)

    def test_process_folder_invalids(self):
        self.assertIsNone(sync.process_folder(item=None, destination_path=self.destination_path,
                                              filters=self.filters['folders'], root=self.root))
        self.assertIsNone(sync.process_folder(item=self.drive[self.items[1]], destination_path=None,
                                              filters=self.filters['folders'], root=self.root))
        self.assertIsNone(sync.process_folder(item=self.drive[self.items[1]], destination_path=self.destination_path,
                                              filters=None, root=self.root))
        self.assertIsNone(sync.process_folder(item=self.drive[self.items[1]], destination_path=self.destination_path,
                                              filters=self.filters['folders'], root=None))

    def test_file_exists_valid(self):
        # File does not exist
        self.assertFalse(sync.file_exists(item=self.file_item, local_file=self.local_file_path))
        # File exists
        sync.download_file(item=self.file_item, local_file=self.local_file_path)
        actual = sync.file_exists(item=self.file_item, local_file=self.local_file_path)
        self.assertTrue(actual)

    def test_file_exists_invalid(self):
        self.assertFalse(sync.file_exists(item=None, local_file=self.local_file_path))
        self.assertFalse(sync.file_exists(item=self.file_item, local_file=None))

    def test_download_file_valids(self):
        self.assertTrue(sync.download_file(item=self.file_item, local_file=self.local_file_path))

    def test_download_file_invalids(self):
        self.assertFalse(sync.download_file(item=None, local_file=self.local_file_path))
        self.assertFalse(sync.download_file(item=self.file_item, local_file=None))
        self.assertFalse(sync.download_file(item=self.file_item,
                                            local_file=os.path.join(self.destination_path, 'non-existent-folder',
                                                                    self.file_name)))

    def test_process_file_valids(self):
        files = set()
        self.assertTrue(sync.process_file(item=self.file_item, destination_path=self.destination_path,
                                          filters=self.filters['file_extensions'], files=files))
        self.assertTrue(len(files) == 1)

    def test_process_file_invalids(self):
        files = set()
        self.assertFalse(sync.process_file(item=None, destination_path=self.destination_path,
                                           filters=self.filters['file_extensions'], files=files))
        self.assertFalse(sync.process_file(item=self.file_item, destination_path=None,
                                           filters=self.filters['file_extensions'], files=files))
        self.assertFalse(sync.process_file(item=self.file_item, destination_path=self.destination_path,
                                           filters=None, files=files))
        self.assertFalse(sync.process_file(item=self.file_item, destination_path=self.destination_path,
                                           filters=self.filters['file_extensions'], files=None))
        # Unwanted file
        original_filters = dict(self.filters)
        del self.filters['file_extensions']
        self.assertFalse(sync.process_file(item=self.file_item, destination_path=self.destination_path,
                                           filters=self.filters, files=files))
        self.assertTrue(len(files) == 0)
        self.filters = original_filters
        # Existing file
        sync.download_file(item=self.file_item, local_file=self.local_file_path)
        self.assertFalse(sync.process_file(item=self.file_item, destination_path=self.destination_path,
                                           filters=self.filters, files=files))

    def test_remove_obsolete_valids(self):
        obsolete_path = os.path.join(self.destination_path, 'obsolete')
        os.mkdir(obsolete_path)
        obsolete_file_path = os.path.join(obsolete_path, os.path.basename(__file__))
        shutil.copyfile(__file__, obsolete_file_path)
        # Remove the file
        files = set()
        files.add(obsolete_path)
        actual = sync.remove_obsolete(destination_path=self.destination_path, files=files)
        self.assertTrue(len(actual) == 1)
        self.assertFalse(os.path.isfile(obsolete_file_path))
        # Remove the directory
        files.remove(obsolete_path)
        actual = sync.remove_obsolete(destination_path=self.destination_path, files=files)
        self.assertTrue(len(actual) == 1)
        self.assertFalse(os.path.isdir(obsolete_path))
        # Remove the directory with file
        os.mkdir(obsolete_path)
        shutil.copyfile(__file__, obsolete_file_path)
        actual = sync.remove_obsolete(destination_path=self.destination_path, files=files)
        self.assertTrue(len(actual) > 0)
        self.assertFalse(os.path.isdir(obsolete_path))
        self.assertFalse(os.path.isfile(obsolete_file_path))

    def test_remove_obsolete_invalids(self):
        obsolete_path = os.path.join(self.destination_path, 'obsolete')
        self.assertTrue(len(sync.remove_obsolete(destination_path=None, files=set())) == 0)
        self.assertTrue(len(sync.remove_obsolete(destination_path=obsolete_path, files=None)) == 0)

    def test_sync_directory_valids(self):
        # Without remove
        actual = sync.sync_directory(drive=self.drive, destination_path=self.destination_path, root=self.root,
                                     items=self.drive.dir(), top=True, filters=self.filters, remove=False)
        self.assertTrue(len(actual) == 4)
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, 'pyiCloud')))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, 'pyiCloud', 'Test')))
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, 'pyiCloud', 'Test', 'Document scanne 2.pdf')))
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, 'pyiCloud', 'Test', 'Scanned document 1.pdf')))
        # With remove
        os.mkdir(os.path.join(self.destination_path, 'obsolete'))
        shutil.copyfile(__file__, os.path.join(self.destination_path, 'obsolete', 'obsolete.py'))
        actual = sync.sync_directory(drive=self.drive, destination_path=self.destination_path, root=self.root,
                                     items=self.drive.dir(), top=True, filters=self.filters, remove=True)
        self.assertTrue(len(actual) == 4)
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, 'pyiCloud')))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, 'pyiCloud', 'Test')))
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, 'pyiCloud', 'Test', 'Document scanne 2.pdf')))
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, 'pyiCloud', 'Test', 'Scanned document 1.pdf')))

    def test_sync_directory_invalids(self):
        self.assertTrue(0 == len(sync.sync_directory(drive=None, destination_path=self.destination_path, root=self.root,
                                                     items=self.drive.dir(), top=True, filters=self.filters,
                                                     remove=False)))
        self.assertTrue(0 == len(sync.sync_directory(drive=self.drive, destination_path=None, root=self.root,
                                                     items=self.drive.dir(), top=True, filters=self.filters,
                                                     remove=False)))
        self.assertTrue(
            0 == len(sync.sync_directory(drive=self.drive, destination_path=self.destination_path, root=None,
                                         items=self.drive.dir(), top=True, filters=self.filters,
                                         remove=False)))
        self.assertTrue(0 == len(sync.sync_directory(drive=self.drive, destination_path=self.destination_path,
                                                     root=self.root, items=None, top=True, filters=self.filters,
                                                     remove=False)))

    @patch('time.sleep')
    @patch(target='keyring.get_password', return_value=data.VALID_PASSWORD)
    @patch(target='src.config_parser.get_username', return_value=data.AUTHENTICATED_USER)
    @patch('pyicloud.PyiCloudService')
    @patch('src.config_parser.read_config')
    def test_sync_drive_valids(self, mock_read_config, mock_service, mock_get_username, mock_get_password, mock_sleep):
        mock_service = self.service
        config = self.config.copy()
        config['settings']['destination'] = self.destination_path
        mock_read_config.return_value = config
        self.assertIsNone(sync.sync_drive())
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, 'pyiCloud')))
        self.assertTrue(os.path.isdir(os.path.join(self.destination_path, 'pyiCloud', 'Test')))
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, 'pyiCloud', 'Test', 'Document scanne 2.pdf')))
        self.assertTrue(
            os.path.isfile(os.path.join(self.destination_path, 'pyiCloud', 'Test', 'Scanned document 1.pdf')))

        mock_get_username.return_value = data.REQUIRES_2FA_USER
        self.assertIsNone(sync.sync_drive())

        mock_get_password.return_value = None
        self.assertIsNone(sync.sync_drive())

        mock_sleep.side_effect = Exception()
        config['settings']['sync_interval'] = 1
        with self.assertRaises(Exception):
            sync.sync_drive()
