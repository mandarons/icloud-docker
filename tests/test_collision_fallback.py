"""Filename-collision fallback in simple format.

Added 2026-05-27. When two distinct iCloud photos share a human filename
(e.g. both are ``IMG_1234.HEIC`` because two iPhones reset their counters),
the second one must NOT silently overwrite the first. Falls back to the
metadata-suffix path for the colliding photo so both files coexist.

Without this, ``filename_format: simple`` would lose data — unacceptable
for a backup tool. With it, plain photos still get plain names; only
collisions get suffixes.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch


def _fake_photo(filename, photo_id, original_size):
    photo = MagicMock()
    photo.filename = filename
    photo.id = photo_id
    photo.versions = {"original": {"type": "public.heic", "size": original_size}}
    photo.created = MagicMock()
    return photo


class TestCollisionFallback(unittest.TestCase):
    """collect_download_task routes colliding photos to suffix names."""

    def setUp(self):
        # Make sure we're in simple mode for these tests.
        from src.photo_path_utils import set_default_filename_format

        set_default_filename_format("simple")
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        from src.photo_path_utils import set_default_filename_format

        set_default_filename_format("metadata")
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_collision_uses_simple_path(self):
        """First-ever download with no existing file → plain name, task returned."""
        from src.photo_download_manager import collect_download_task

        photo = _fake_photo("IMG_AAAA.HEIC", "id-aaaa", 12345)
        task = collect_download_task(
            photo,
            "original",
            self.tmp,
            set(),
            folder_format=None,
            hardlink_registry=None,
        )
        assert task is not None
        assert task.photo_path.endswith("IMG_AAAA.HEIC")
        # Suffix form NOT in the path
        assert "__original__" not in task.photo_path

    def test_same_photo_resync_skips(self):
        """Same photo (matching size at plain path) → no task (skip)."""
        from src.photo_download_manager import collect_download_task

        photo = _fake_photo("IMG_BBBB.HEIC", "id-bbbb", 12345)
        # Pre-create the file at the plain path with matching size
        plain_path = os.path.join(self.tmp, "IMG_BBBB.HEIC")
        with open(plain_path, "wb") as f:
            f.write(b"x" * 12345)

        task = collect_download_task(
            photo,
            "original",
            self.tmp,
            set(),
            folder_format=None,
            hardlink_registry=None,
        )
        assert task is None  # already-present photo, skipped

    def test_collision_falls_back_to_suffix(self):
        """Plain path occupied by a DIFFERENT photo → suffix path used.

        Simulates the iCloud-collision scenario: two distinct iCloud photos
        named ``IMG_CCCC.HEIC`` with different sizes. The first lives at the
        plain path; the second must NOT overwrite it.
        """
        from src.photo_download_manager import collect_download_task

        # Pre-create the "first" photo at the plain path (e.g. from a prior
        # boredazfcuk sync) — 9999 bytes.
        plain_path = os.path.join(self.tmp, "IMG_CCCC.HEIC")
        with open(plain_path, "wb") as f:
            f.write(b"x" * 9999)

        # Current photo is a DIFFERENT iCloud asset with the same human name
        # but a different size (12345 bytes).
        photo = _fake_photo("IMG_CCCC.HEIC", "different-id-cccc", 12345)

        task = collect_download_task(
            photo,
            "original",
            self.tmp,
            set(),
            folder_format=None,
            hardlink_registry=None,
        )
        # Task returned — colliding photo gets the suffix path.
        assert task is not None
        assert task.photo_path != plain_path  # NOT overwriting the first file
        assert "__original__" in task.photo_path
        assert task.photo_path.endswith(".HEIC")
        # First-photo file at plain path is untouched (still 9999 bytes)
        assert os.path.getsize(plain_path) == 9999

    def test_collision_suffix_already_downloaded_skips(self):
        """If the suffix path also already exists with matching size → skip.

        This is the second-and-later-sync of a previously-collided photo:
        plain path belongs to photo A, suffix path belongs to photo B, both
        are stable.
        """
        from src.photo_download_manager import collect_download_task

        # Photo A occupies the plain path
        plain_path = os.path.join(self.tmp, "IMG_DDDD.HEIC")
        with open(plain_path, "wb") as f:
            f.write(b"a" * 100)

        # Photo B (different photo, same name) — must go to suffix path
        photo_b = _fake_photo("IMG_DDDD.HEIC", "photo-b-id", 200)

        # Pre-create the suffix path with photo B's size
        import base64 as _b64

        b64id = _b64.urlsafe_b64encode(b"photo-b-id").decode()
        suffix_path = os.path.join(self.tmp, f"IMG_DDDD__original__{b64id}.HEIC")
        with open(suffix_path, "wb") as f:
            f.write(b"b" * 200)

        task = collect_download_task(
            photo_b,
            "original",
            self.tmp,
            set(),
            folder_format=None,
            hardlink_registry=None,
        )
        # Both photos are already on disk — no work needed.
        assert task is None

    def test_metadata_mode_no_collision_logic(self):
        """In metadata (default) mode, collision logic is bypassed — already-
        unique suffix names cannot collide."""
        from src.photo_path_utils import set_default_filename_format

        set_default_filename_format("metadata")

        from src.photo_download_manager import collect_download_task

        photo = _fake_photo("IMG_EEEE.HEIC", "id-eeee", 12345)
        task = collect_download_task(
            photo,
            "original",
            self.tmp,
            set(),
            folder_format=None,
            hardlink_registry=None,
        )
        assert task is not None
        # In metadata mode the path includes the suffix from the start
        assert "__original__" in task.photo_path
