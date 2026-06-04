"""Regression tests: flat package bundles must not re-download every sync.

A package kept on disk as a flat single-file bundle (an unrecognised-mime
package, or any package downloaded with ``flatten_packages: true``) has an
on-disk byte count equal to the package-download archive size, which never
equals ``item.size`` (the package's *logical* size iCloud reports). Because
``file_exists`` compares against ``item.size`` it sees a spurious size
mismatch and the file re-downloads on every sync -- pure wasted bandwidth.

``package_bundle_unchanged`` fixes this: when the item is a package and the
on-disk bundle's mtime already matches the remote ``date_modified`` (which
``download_file`` stamps via ``os.utime``), the bytes are unchanged and the
re-download is skipped. ``is_package`` is already called in the outdated-file
path, so the skip adds no extra network round-trip.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import datetime
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import tests  # noqa: F401  — env setup
from src import drive_file_existence, sync_drive
from src.drive_parallel_download import collect_file_for_download


def _bundle_item(name="Investor Pitch.key", logical_size=4096, modified=None):
    """A MagicMock iCloud item that behaves like a package: its ``size`` is the
    package's logical size (deliberately NOT the on-disk bundle byte count)."""
    item = MagicMock()
    item.name = name
    item.size = logical_size
    item.date_modified = modified or datetime.datetime(2021, 3, 7, 12, 0, 0)
    return item


def _write_bundle(path, item, on_disk_bytes=b"x" * 50):
    """Write a flat bundle on disk with mtime stamped to item.date_modified
    (as download_file does) and a byte count that differs from item.size."""
    with open(path, "wb") as f:
        f.write(on_disk_bytes)
    mtime = int(item.date_modified.timestamp())
    os.utime(path, (mtime, mtime))
    # Sanity: this is exactly the pathological condition — size differs.
    assert os.path.getsize(path) != item.size


class TestPackageBundleUnchanged(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_true_when_mtime_matches(self):
        item = _bundle_item()
        path = os.path.join(self.tmp, "a.key")
        _write_bundle(path, item)
        self.assertTrue(drive_file_existence.package_bundle_unchanged(item=item, local_file=path))

    def test_false_when_mtime_differs(self):
        item = _bundle_item()
        path = os.path.join(self.tmp, "a.key")
        _write_bundle(path, item)
        newer = int(item.date_modified.timestamp()) + 5
        os.utime(path, (newer, newer))
        self.assertFalse(drive_file_existence.package_bundle_unchanged(item=item, local_file=path))

    def test_false_when_missing(self):
        item = _bundle_item()
        self.assertFalse(
            drive_file_existence.package_bundle_unchanged(
                item=item,
                local_file=os.path.join(self.tmp, "nope.key"),
            ),
        )

    def test_false_when_directory(self):
        item = _bundle_item()
        d = os.path.join(self.tmp, "pkg.key")
        os.makedirs(d)
        self.assertFalse(drive_file_existence.package_bundle_unchanged(item=item, local_file=d))

    def test_false_when_no_item_or_path(self):
        self.assertFalse(drive_file_existence.package_bundle_unchanged(item=None, local_file="x"))
        self.assertFalse(drive_file_existence.package_bundle_unchanged(item=_bundle_item(), local_file=None))


class TestCollectSkipsUnchangedBundle(unittest.TestCase):
    """The active parallel-download path must skip an unchanged flat bundle."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _collect(self, item):
        return collect_file_for_download(
            item=item,
            destination_path=self.tmp,
            filters=None,
            ignore=None,
            files=set(),
            config=None,
        )

    @patch("src.drive_parallel_download.is_package", return_value=True)
    def test_unchanged_bundle_is_skipped(self, _mock_is_pkg):
        item = _bundle_item()
        _write_bundle(os.path.join(self.tmp, item.name), item)
        # file_exists() fails on the size mismatch; the new guard must skip anyway.
        self.assertIsNone(self._collect(item))

    @patch("src.drive_parallel_download.is_package", return_value=True)
    def test_changed_bundle_redownloads(self, _mock_is_pkg):
        item = _bundle_item()
        path = os.path.join(self.tmp, item.name)
        _write_bundle(path, item)
        newer = int(item.date_modified.timestamp()) + 99
        os.utime(path, (newer, newer))  # remote changed → mtime differs
        info = self._collect(item)
        self.assertIsNotNone(info)
        self.assertTrue(info["is_package"])

    @patch("src.drive_parallel_download.is_package", return_value=False)
    def test_non_package_outdated_file_still_redownloads(self, _mock_is_pkg):
        # A genuinely-changed regular file (not a package) must NOT be skipped.
        item = _bundle_item(name="report.pdf")
        _write_bundle(os.path.join(self.tmp, item.name), item)
        info = self._collect(item)
        self.assertIsNotNone(info)
        self.assertFalse(info["is_package"])


class TestProcessFileSkipsUnchangedBundle(unittest.TestCase):
    """The legacy process_file path gets the same guard."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("src.sync_drive.is_package", return_value=True)
    def test_unchanged_bundle_is_skipped(self, _mock_is_pkg):
        item = _bundle_item()
        _write_bundle(os.path.join(self.tmp, item.name), item)
        result = sync_drive.process_file(
            item=item,
            destination_path=self.tmp,
            filters=None,
            ignore=None,
            files=set(),
        )
        self.assertFalse(result)  # skipped → not processed/downloaded


if __name__ == "__main__":
    unittest.main()
