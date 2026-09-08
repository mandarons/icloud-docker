"""Tests for ``photos.preserve_originals_as_bak`` — hide untouched originals
of edited photos via the ``.original.bak`` filename suffix.

Added 2026-05-27. When ``preserve_originals_as_bak: true`` and the user has
both ``original`` and ``original_alt`` in ``file_sizes``, edited photos
land as two files: the alt visible to photo browsers, the original hidden
via a ``.bak`` extension. Unedited photos are unaffected.
"""

import unittest
from unittest.mock import MagicMock

from src import config_parser
from src.photo_path_utils import (
    generate_photo_filename_with_metadata,
    set_preserve_originals_as_bak,
)


def _photo_with_alt(filename="IMG_1234.HEIC", photo_id="abc"):
    """Edited photo — has both original and original_alt versions."""
    photo = MagicMock()
    photo.filename = filename
    photo.id = photo_id
    photo.versions = {
        "original": {"type": "public.heic", "size": 12345},
        "original_alt": {"type": "public.jpeg", "size": 8000},
    }
    return photo


def _photo_unedited(filename="IMG_5678.HEIC", photo_id="def"):
    """Unedited photo — has only original (no original_alt)."""
    photo = MagicMock()
    photo.filename = filename
    photo.id = photo_id
    photo.versions = {"original": {"type": "public.heic", "size": 12345}}
    return photo


class TestGetPhotosPreserveOriginalsAsBak(unittest.TestCase):
    def test_default_is_false(self):
        assert config_parser.get_photos_preserve_originals_as_bak({}) is False

    def test_false_is_false(self):
        config = {"photos": {"preserve_originals_as_bak": False}}
        assert config_parser.get_photos_preserve_originals_as_bak(config) is False

    def test_true_is_true(self):
        config = {"photos": {"preserve_originals_as_bak": True}}
        assert config_parser.get_photos_preserve_originals_as_bak(config) is True

    def test_truthy_values_normalised_to_true(self):
        config = {"photos": {"preserve_originals_as_bak": "yes"}}
        assert config_parser.get_photos_preserve_originals_as_bak(config) is True


class TestFilenameSuffixApplied(unittest.TestCase):
    """The .original.bak suffix is applied to original of edited photos only."""

    def setUp(self):
        set_preserve_originals_as_bak(True)

    def tearDown(self):
        set_preserve_originals_as_bak(False)

    def test_edited_photo_original_gets_bak_suffix(self):
        photo = _photo_with_alt("IMG_1234.HEIC", "abc")
        name = generate_photo_filename_with_metadata(photo, "original")
        assert name.endswith(".HEIC.original.bak"), f"got {name!r}"
        # Still has the metadata-suffix portion ahead of .HEIC.original.bak
        assert "IMG_1234__original__" in name

    def test_edited_photo_alt_does_NOT_get_bak_suffix(self):
        """The alt is the visible 'current view' file — must not be hidden."""
        photo = _photo_with_alt("IMG_1234.HEIC", "abc")
        name = generate_photo_filename_with_metadata(photo, "original_alt")
        assert not name.endswith(".bak"), f"got {name!r}"

    def test_unedited_photo_original_does_NOT_get_bak_suffix(self):
        """Photos without an alt version should keep their normal name."""
        photo = _photo_unedited("IMG_5678.HEIC", "def")
        name = generate_photo_filename_with_metadata(photo, "original")
        assert not name.endswith(".bak"), f"got {name!r}"
        assert name.endswith(".HEIC")

    def test_medium_size_does_NOT_get_bak_suffix(self):
        """Only the `original` size is hidden — `medium` and others are normal."""
        photo = _photo_with_alt("IMG_1234.HEIC", "abc")
        # Add a medium version so generate_photo_filename_with_metadata works
        photo.versions["medium"] = {"type": "public.jpeg", "size": 4000}
        name = generate_photo_filename_with_metadata(photo, "medium")
        assert not name.endswith(".bak"), f"got {name!r}"


class TestFilenameSuffixNotAppliedWhenToggleOff(unittest.TestCase):
    """With the toggle off (default), edited photos' originals get normal names."""

    def setUp(self):
        set_preserve_originals_as_bak(False)

    def test_edited_photo_original_no_bak_when_toggle_off(self):
        photo = _photo_with_alt("IMG_1234.HEIC", "abc")
        name = generate_photo_filename_with_metadata(photo, "original")
        assert not name.endswith(".bak"), f"got {name!r}"
        assert name.endswith(".HEIC")


class TestPartialCloudkitRecordSafe(unittest.TestCase):
    """If reading photo.versions raises, treat as 'no alt' (don't suffix)."""

    def setUp(self):
        set_preserve_originals_as_bak(True)

    def tearDown(self):
        set_preserve_originals_as_bak(False)

    def test_versions_raises_falls_through_to_normal_name(self):
        """A partial CloudKit record where ``photo.versions`` raises
        must not crash filename generation. Treat-as-no-alt soft path
        is exercised — result is the normal name with no ``.bak``."""

        # Use a dedicated stub class instead of mutating ``MagicMock``'s
        # class via ``type(photo).versions = property(...)`` — that
        # pattern monkey-patches MagicMock globally and leaks into every
        # later test that touches ``MagicMock().versions``.
        class _BrokenPhoto:
            filename = "IMG_9999.HEIC"
            id = "xyz"

            @property
            def versions(self):
                msg = "broken record"
                raise RuntimeError(msg)

        name = generate_photo_filename_with_metadata(_BrokenPhoto(), "original")
        assert not name.endswith(".bak"), f"got {name!r}"



class TestSyncGateRequiresOriginalAlt(unittest.TestCase):
    """The ``sync_photos.sync_photos`` orchestrator must only flip the
    ``set_preserve_originals_as_bak`` toggle when ``original_alt`` is
    actually in the configured ``file_sizes``. Otherwise the suffix
    hides the original AND the visible edited view is never downloaded
    -- the photo "disappears" from photo browsers.

    The toggle defaults to OFF, so we observe the boolean the
    orchestrator passes to ``set_preserve_originals_as_bak`` via patch.
    """

    def setUp(self):
        set_preserve_originals_as_bak(False)

    def tearDown(self):
        set_preserve_originals_as_bak(False)

    def _config(self, file_sizes):
        return {
            "photos": {
                "destination": "photos",
                "preserve_originals_as_bak": True,
                "filters": {
                    "libraries": ["PrimarySync"],
                    "file_sizes": file_sizes,
                },
            },
        }

    def _run_with_config(self, config):
        from unittest.mock import MagicMock, patch

        from src import sync_photos

        api_photos = MagicMock()
        api_photos.libraries = {"PrimarySync": MagicMock(all=[], albums={})}
        with patch.object(
            sync_photos.config_parser,
            "prepare_photos_destination",
            return_value="/tmp/photos",
        ), patch.object(
            sync_photos, "_sync_albums_by_configuration", return_value=(0, 0),
        ), patch.object(
            sync_photos, "remove_obsolete_files",
        ), patch(
            "src.photo_path_utils.set_preserve_originals_as_bak",
        ) as fake_set:
            sync_photos.sync_photos(config=config, photos=api_photos)
        return fake_set

    def test_gate_FALSE_when_original_alt_not_in_file_sizes(self):
        """preserve_originals_as_bak=true BUT original_alt not requested
        -> the orchestrator must call ``set_preserve_originals_as_bak(False)``
        so the original lands at its normal (visible) name. Otherwise
        the photo has no visible representation on disk."""
        fake_set = self._run_with_config(self._config(["original"]))
        # set_preserve_originals_as_bak called with False (or never called).
        if fake_set.call_args_list:
            last_arg = fake_set.call_args_list[-1].args[0]
            assert last_arg is False, f"expected False, got {last_arg!r}"

    def test_gate_TRUE_when_original_alt_IS_in_file_sizes(self):
        """preserve_originals_as_bak=true AND original_alt requested
        -> the toggle activates; the edited "current view" lands
        visibly while the untouched original goes to .bak."""
        fake_set = self._run_with_config(self._config(["original", "original_alt"]))
        # Last call was True.
        assert fake_set.call_args_list, "set_preserve_originals_as_bak never called"
        last_arg = fake_set.call_args_list[-1].args[0]
        assert last_arg is True, f"expected True, got {last_arg!r}"

    def test_gate_FALSE_when_config_false_even_if_original_alt_present(self):
        """preserve_originals_as_bak=false short-circuits regardless of
        file_sizes."""
        cfg = self._config(["original", "original_alt"])
        cfg["photos"]["preserve_originals_as_bak"] = False
        fake_set = self._run_with_config(cfg)
        if fake_set.call_args_list:
            last_arg = fake_set.call_args_list[-1].args[0]
            assert last_arg is False, f"expected False, got {last_arg!r}"
