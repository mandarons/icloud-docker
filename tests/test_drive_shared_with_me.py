"""A folder someone else shared into this Drive is skipped, and kept."""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src import (
    drive_sync_directory,
    sync_drive,  # noqa: F401 - loads drive_sync_directory without a cycle
)


class _Item:
    def __init__(self, name, kind="folder", data=None):
        self.name = name
        self.type = kind
        self.data = data or {}

    def dir(self):
        message = "a shared-with-me folder must not be listed"
        raise AssertionError(message)


class TestSharedWithMe(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_skipped_and_its_local_copy_survives_cleanup(self):
        kept = os.path.join(self.root, "Their Folder", "photo.jpg")
        os.makedirs(os.path.dirname(kept))
        with open(kept, "w") as f:
            f.write("x")
        stale = os.path.join(self.root, "gone.txt")
        with open(stale, "w") as f:
            f.write("x")
        drive = {"a": _Item("Their Folder", data={"share": "TO_ME", "owner": {"firstName": "A"}})}
        with patch.object(drive_sync_directory, "_process_folder_item") as process:
            files = drive_sync_directory.sync_directory(
                drive=drive,
                destination_path=self.root,
                items=["a"],
                root=self.root,
                remove=True,
                config={},
            )
        process.assert_not_called()
        self.assertTrue(os.path.exists(kept))
        self.assertFalse(os.path.exists(stale))
        self.assertIn(kept, files)

    def test_own_and_shared_by_me_folders_are_synced(self):
        for data in ({}, {"share": "BY_ME"}, {"shareCount": 1}):
            with self.subTest(data=data):
                self.assertFalse(drive_sync_directory._shared_with_me(_Item("x", data=data)))  # noqa: SLF001
        self.assertTrue(drive_sync_directory._shared_with_me(_Item("x", data={"share": "TO_ME"})))  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
