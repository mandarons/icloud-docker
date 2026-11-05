"""Copies of one photo, each with its own edit.

Photos' Duplicate, and editors such as Snapseed that save an edit as a new
photo, add a ``CPLAsset`` record pointing at the same ``CPLMaster``. Every
copy shares the master's ``recordName`` (``photo.id``), while each copy's edit
lives on its own asset record. These use icloudpy's real ``PhotoAsset`` over
records shaped like its fixtures; every id and value is synthetic.
"""

import base64
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from icloudpy.services.photos import PhotoAsset

from src.hardlink_registry import HardlinkRegistry
from src.photo_download_manager import collect_download_task, generate_photo_path
from src.photo_path_utils import (
    generate_photo_filename_with_metadata,
    set_default_filename_format,
    version_record_id,
)

MASTER = "MASTER-7039"


def _copy(asset_name, edit_size):
    master = {
        "recordName": MASTER,
        "recordType": "CPLMaster",
        "fields": {
            "filenameEnc": {"value": base64.b64encode(b"IMG_7039.HEIC").decode()},
            "itemType": {"value": "public.heic"},
            "resOriginalRes": {
                "value": {"size": 5000, "downloadURL": "https://cdn.invalid/o"},
            },
            "resOriginalFileType": {"value": "public.heic"},
        },
    }
    asset = {
        "recordName": asset_name,
        "recordType": "CPLAsset",
        "fields": {
            "assetDate": {"value": 1700000000000},
            "addedDate": {"value": 1700000000000},
            "resJPEGFullRes": {
                "value": {
                    "size": edit_size,
                    "downloadURL": f"https://cdn.invalid/{asset_name}",
                },
            },
            "resJPEGFullFileType": {"value": "public.jpeg"},
        },
    }
    return PhotoAsset(MagicMock(), master, asset)


def _b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode()


class TestEachCopysEditGetsItsOwnName(unittest.TestCase):
    def setUp(self):
        set_default_filename_format("metadata")
        self.addCleanup(set_default_filename_format, "metadata")
        self.first = _copy("ASSET-A", 100)
        self.second = _copy("ASSET-B", 200)

    def test_both_copies_share_the_master_id(self):
        self.assertEqual(self.first.id, self.second.id)

    def test_the_edits_no_longer_resolve_to_one_file(self):
        first = generate_photo_filename_with_metadata(self.first, "full")
        second = generate_photo_filename_with_metadata(self.second, "full")
        self.assertNotEqual(first, second)
        self.assertIn(_b64("ASSET-A"), first)

    def test_originals_keep_their_names(self):
        """The original is master-carried: its name, and every existing
        original on disk, is unchanged."""
        self.assertEqual(version_record_id(self.first, "original"), MASTER)
        self.assertEqual(
            generate_photo_filename_with_metadata(self.first, "original"),
            f"IMG_7039__original__{_b64(MASTER)}.HEIC",
        )

    def test_one_copys_edit_is_not_hardlinked_as_anothers(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        registry = HardlinkRegistry()
        registry.register_photo_path(
            version_record_id(self.first, "full"), "full", os.path.join(tmp, "a.jpeg"),
        )
        task = collect_download_task(self.second, "full", tmp, set(), None, registry)
        self.assertIsNotNone(task)
        self.assertIsNone(task.hardlink_source)


class TestAnEditUnderTheOldNameIsMovedNotDownloaded(unittest.TestCase):
    """Before this, an edit was named after the master record."""

    def setUp(self):
        set_default_filename_format("metadata")
        self.addCleanup(set_default_filename_format, "metadata")
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.photo = _copy("ASSET-A", 3)
        self.old = os.path.join(self.tmp, f"IMG_7039__full__{_b64(MASTER)}.jpeg")

    def _write_old(self, content):
        with open(self.old, "wb") as f:
            f.write(content)

    def test_a_file_of_the_right_size_is_renamed(self):
        self._write_old(b"abc")
        path = generate_photo_path(self.photo, "full", self.tmp, None)
        self.assertTrue(path.endswith(f"IMG_7039__full__{_b64('ASSET-A')}.jpeg"))
        self.assertTrue(os.path.isfile(path))
        self.assertFalse(os.path.exists(self.old))

    def test_another_copys_edit_is_left_where_it_is(self):
        """The old name was shared, so the file there may be another copy's
        edit; a different size says it is not this one."""
        self._write_old(b"abcdef")
        path = generate_photo_path(self.photo, "full", self.tmp, None)
        self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.isfile(self.old))


if __name__ == "__main__":
    unittest.main()
