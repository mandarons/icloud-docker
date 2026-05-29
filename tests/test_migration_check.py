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


class TestCheckLibrary(unittest.TestCase):
    """Behaviour of the per-library walk."""

    def setUp(self):
        # mandarons' filename_format singleton needs setting because
        # check_migration normally does it but here we test the inner
        # walker in isolation.
        from src.photo_path_utils import set_default_filename_format

        set_default_filename_format("simple")

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


if __name__ == "__main__":
    unittest.main()
