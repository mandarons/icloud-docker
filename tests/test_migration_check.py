"""Tests for ``src.migration_check.check_library`` — the per-photo
file-existence check driven by ``--dry-run --check-files``."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import tempfile
import unittest
from unittest.mock import MagicMock

import tests  # noqa: F401  — env setup
from src import migration_check


def _fake_photo(filename: str, size: int, year: int = 2024, month: int = 1):
    """Build a MagicMock that quacks like an icloudpy PhotoAsset."""
    from datetime import datetime

    photo = MagicMock()
    photo.filename = filename
    photo.created = datetime(year, month, 15)
    photo.versions = {"original": {"size": size, "type": "public.heic"}}
    photo.id = filename.encode().hex()  # stable, unique-ish id for testing
    return photo


def _fake_library(photos: list):
    """Wrap a list of photo mocks in an object shaped like a PhotoLibrary."""
    library = MagicMock()
    library.albums = {"All Photos": photos}
    return library


# Whether the upstream supports the "simple" filename_format toggle.
# When False, the simple-format-dependent assertions are skipped (the
# inner walker still functions; the tests would just be comparing
# metadata-suffixed filenames against simple-named test fixtures and
# always report not_found). Lifts cleanly once
# feat/photos-filename-format-simple is merged upstream.
_SIMPLE_FORMAT_AVAILABLE = hasattr(
    __import__("src.photo_path_utils", fromlist=["x"]),
    "set_default_filename_format",
)


@unittest.skipUnless(
    _SIMPLE_FORMAT_AVAILABLE,
    "Requires feat/photos-filename-format-simple to be merged upstream "
    "for the inner walker to produce IMG_N.HEIC-style names that match "
    "these size-comparison fixtures.",
)
class TestCheckLibrary(unittest.TestCase):
    """Behaviour of the per-library walk."""

    def setUp(self):
        # mandarons' filename_format singleton needs setting because
        # check_migration normally does it but here we test the inner
        # walker in isolation. Imported via migration_check so the
        # fallback shim works when feat/photos-filename-format-simple
        # isn't merged yet on upstream main.
        migration_check.set_default_filename_format("simple")

    def test_empty_library(self):
        with tempfile.TemporaryDirectory() as base:
            result = migration_check.check_library(
                library=_fake_library([]),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},
                folder_format=None,
                sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 0)
            self.assertEqual(result["stats"]["not_found"], 0)
            self.assertEqual(result["checked"], 0)

    def test_all_photos_present_and_correct_size(self):
        with tempfile.TemporaryDirectory() as base:
            # Create three photos on disk at the expected paths with the
            # expected sizes; check_library should report all would_skip.
            photos = []
            for i, size in enumerate([1000, 2000, 3000]):
                name = f"IMG_{i}.HEIC"
                path = os.path.join(base, name)
                with open(path, "wb") as f:
                    f.write(b"x" * size)
                photos.append(_fake_photo(name, size))

            result = migration_check.check_library(
                library=_fake_library(photos),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},  # empty mapping → fall through to base
                folder_format=None,
                sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 3)
            self.assertEqual(result["stats"]["size_mismatch"], 0)
            self.assertEqual(result["stats"]["not_found"], 0)
            self.assertEqual(result["checked"], 3)

    def test_all_photos_missing(self):
        with tempfile.TemporaryDirectory() as base:
            photos = [_fake_photo(f"IMG_{i}.HEIC", 1000 + i) for i in range(3)]
            result = migration_check.check_library(
                library=_fake_library(photos),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},
                folder_format=None,
                sample=0,
            )
            self.assertEqual(result["stats"]["not_found"], 3)
            self.assertEqual(result["stats"]["would_skip"], 0)

    def test_size_mismatch_counts_separately_from_not_found(self):
        with tempfile.TemporaryDirectory() as base:
            # One file present at correct size, one at wrong size, one missing.
            with open(os.path.join(base, "IMG_a.HEIC"), "wb") as f:
                f.write(b"x" * 1000)  # matches
            with open(os.path.join(base, "IMG_b.HEIC"), "wb") as f:
                f.write(b"x" * 500)  # wrong size — expected 2000

            photos = [
                _fake_photo("IMG_a.HEIC", 1000),
                _fake_photo("IMG_b.HEIC", 2000),
                _fake_photo("IMG_c.HEIC", 3000),  # no file on disk
            ]
            result = migration_check.check_library(
                library=_fake_library(photos),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},
                folder_format=None,
                sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 1)
            self.assertEqual(result["stats"]["size_mismatch"], 1)
            self.assertEqual(result["stats"]["not_found"], 1)
            # samples capture the per-status examples
            self.assertEqual(len(result["samples"]["would_skip"]), 1)
            self.assertEqual(len(result["samples"]["size_mismatch"]), 1)
            # size_mismatch sample carries (path, expected, actual)
            path, expected, actual = result["samples"]["size_mismatch"][0]
            self.assertEqual(expected, 2000)
            self.assertEqual(actual, 500)

    def test_sample_caps_walk_at_N(self):
        """``sample=N`` walks N stride-sampled photos and stops."""
        with tempfile.TemporaryDirectory() as base:
            photos = [_fake_photo(f"IMG_{i}.HEIC", 1000) for i in range(200)]
            result = migration_check.check_library(
                library=_fake_library(photos),
                library_name="PrimarySync",
                photos_base=base,
                mapping={},
                folder_format=None,
                sample=10,
            )
            self.assertEqual(result["checked"], 10)


def _fake_drive_file(name: str, size: int):
    """Build a MagicMock that quacks like an icloudpy Drive file node."""
    node = MagicMock()
    node.name = name
    node.type = "file"
    node.size = size
    return node


def _fake_drive_folder(name: str, children: dict):
    """Build a MagicMock that quacks like an icloudpy Drive folder node.

    ``children`` is a dict mapping child-name → child-mock (file or folder).
    """
    node = MagicMock()
    node.name = name
    node.type = "folder"
    node.dir.return_value = list(children.keys())
    node.__getitem__.side_effect = lambda key: children[key]
    return node


class TestCheckDrive(unittest.TestCase):
    """Behaviour of the iCloud Drive walker."""

    def test_empty_drive(self):
        with tempfile.TemporaryDirectory() as base:
            drive = _fake_drive_folder("root", {})
            result = migration_check.check_drive(
                drive=drive, drive_destination=base, sample=0,
            )
            self.assertEqual(result["checked"], 0)
            self.assertEqual(result["stats"]["would_skip"], 0)
            self.assertEqual(result["stats"]["not_found"], 0)

    def test_all_files_present_at_root(self):
        with tempfile.TemporaryDirectory() as base:
            # Three files on disk with known sizes
            for name, size in [("a.txt", 100), ("b.txt", 200), ("c.txt", 300)]:
                with open(os.path.join(base, name), "wb") as f:
                    f.write(b"x" * size)
            drive = _fake_drive_folder(
                "root",
                {
                    "a.txt": _fake_drive_file("a.txt", 100),
                    "b.txt": _fake_drive_file("b.txt", 200),
                    "c.txt": _fake_drive_file("c.txt", 300),
                },
            )
            result = migration_check.check_drive(
                drive=drive, drive_destination=base, sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 3)
            self.assertEqual(result["stats"]["size_mismatch"], 0)
            self.assertEqual(result["stats"]["not_found"], 0)
            self.assertEqual(result["checked"], 3)

    def test_missing_and_size_mismatch_at_root(self):
        with tempfile.TemporaryDirectory() as base:
            # a.txt matches; b.txt wrong size; c.txt missing.
            with open(os.path.join(base, "a.txt"), "wb") as f:
                f.write(b"x" * 100)
            with open(os.path.join(base, "b.txt"), "wb") as f:
                f.write(b"x" * 50)  # expected 200
            drive = _fake_drive_folder(
                "root",
                {
                    "a.txt": _fake_drive_file("a.txt", 100),
                    "b.txt": _fake_drive_file("b.txt", 200),
                    "c.txt": _fake_drive_file("c.txt", 300),
                },
            )
            result = migration_check.check_drive(
                drive=drive, drive_destination=base, sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 1)
            self.assertEqual(result["stats"]["size_mismatch"], 1)
            self.assertEqual(result["stats"]["not_found"], 1)
            self.assertEqual(len(result["samples"]["size_mismatch"]), 1)
            _, expected, actual = result["samples"]["size_mismatch"][0]
            self.assertEqual(expected, 200)
            self.assertEqual(actual, 50)

    def test_recurses_into_subfolders(self):
        with tempfile.TemporaryDirectory() as base:
            # On-disk: base/sub/leaf.txt @ 42 bytes
            os.makedirs(os.path.join(base, "sub"))
            with open(os.path.join(base, "sub", "leaf.txt"), "wb") as f:
                f.write(b"x" * 42)
            sub_folder = _fake_drive_folder(
                "sub", {"leaf.txt": _fake_drive_file("leaf.txt", 42)},
            )
            drive = _fake_drive_folder("root", {"sub": sub_folder})
            result = migration_check.check_drive(
                drive=drive, drive_destination=base, sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 1)
            self.assertEqual(result["checked"], 1)

    def test_unpacked_package_directory_counts_as_skip_when_size_matches(self):
        """Mandarons-unpacked packages live as directories on disk; sum
        of contained-file sizes must match the package item size."""
        with tempfile.TemporaryDirectory() as base:
            # Package directory with two inner files summing to 150
            pkg_path = os.path.join(base, "Project.band")
            os.makedirs(pkg_path)
            with open(os.path.join(pkg_path, "metadata.plist"), "wb") as f:
                f.write(b"x" * 50)
            with open(os.path.join(pkg_path, "projectdata"), "wb") as f:
                f.write(b"x" * 100)
            drive = _fake_drive_folder(
                "root", {"Project.band": _fake_drive_file("Project.band", 150)},
            )
            result = migration_check.check_drive(
                drive=drive, drive_destination=base, sample=0,
            )
            self.assertEqual(result["stats"]["would_skip"], 1)
            self.assertEqual(result["stats"]["size_mismatch"], 0)

    def test_sample_caps_drive_walk_at_N(self):
        with tempfile.TemporaryDirectory() as base:
            children = {
                f"f{i}.txt": _fake_drive_file(f"f{i}.txt", 100) for i in range(20)
            }
            drive = _fake_drive_folder("root", children)
            result = migration_check.check_drive(
                drive=drive, drive_destination=base, sample=5,
            )
            self.assertEqual(result["checked"], 5)


if __name__ == "__main__":
    unittest.main()
