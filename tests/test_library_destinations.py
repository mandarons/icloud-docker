"""Tests for per-library destination subdirectories.

Added 2026-05-27 as part of feat/per-library-destinations-and-live-photos.
Covers ``config_parser.get_photos_library_destinations`` and the
``_library_destination`` helper threaded through sync_photos.
"""

import os
import tempfile
import unittest

from src import config_parser
from src.sync_photos import _library_destination


class TestGetPhotosLibraryDestinations(unittest.TestCase):
    """get_photos_library_destinations returns dict or {} based on config."""

    def test_returns_empty_dict_when_unset(self):
        config = {"photos": {"destination": "photos"}}
        assert config_parser.get_photos_library_destinations(config) == {}

    def test_returns_empty_dict_when_photos_section_missing(self):
        config = {}
        assert config_parser.get_photos_library_destinations(config) == {}

    def test_returns_mapping_when_configured(self):
        config = {
            "photos": {
                "destination": "photos",
                "library_destinations": {
                    "PrimarySync": "personal",
                    "SharedLibrary": "shared",
                },
            },
        }
        result = config_parser.get_photos_library_destinations(config)
        assert result == {"PrimarySync": "personal", "SharedLibrary": "shared"}

    def test_returns_empty_dict_when_value_is_not_a_dict(self):
        config = {"photos": {"library_destinations": ["foo", "bar"]}}
        assert config_parser.get_photos_library_destinations(config) == {}

    def test_coerces_non_string_keys_and_values_to_str(self):
        config = {
            "photos": {"library_destinations": {123: 456, "PrimarySync": "personal"}},
        }
        result = config_parser.get_photos_library_destinations(config)
        assert result == {"123": "456", "PrimarySync": "personal"}


class TestLibraryDestinationHelper(unittest.TestCase):
    """_library_destination resolves the right on-disk path per library."""

    def test_returns_base_when_no_mapping(self):
        with tempfile.TemporaryDirectory() as base:
            result = _library_destination(base, "PrimarySync", {})
            assert result == base

    def test_returns_base_when_library_not_in_mapping(self):
        with tempfile.TemporaryDirectory() as base:
            mapping = {"PrimarySync": "personal"}
            result = _library_destination(base, "SharedLibrary", mapping)
            # Library not in mapping → fall through to base destination
            assert result == base

    def test_joins_subdir_and_creates_directory(self):
        with tempfile.TemporaryDirectory() as base:
            mapping = {"PrimarySync": "personal"}
            result = _library_destination(base, "PrimarySync", mapping)
            assert result == os.path.join(base, "personal")
            assert os.path.isdir(result)

    def test_creates_nested_subdirectories(self):
        with tempfile.TemporaryDirectory() as base:
            mapping = {"PrimarySync": "by-source/personal"}
            result = _library_destination(base, "PrimarySync", mapping)
            assert result == os.path.join(base, "by-source", "personal")
            assert os.path.isdir(result)

    def test_none_mapping_is_safe(self):
        with tempfile.TemporaryDirectory() as base:
            result = _library_destination(base, "PrimarySync", None)
            assert result == base

    def test_shared_library_alias_matches_guid_named_zone(self):
        """`SharedLibrary` in the config matches Apple's GUID-named shared zones
        (e.g. ``SharedSync-3C977B4A-...``) — users don't have to discover and
        hardcode their per-account GUID."""
        with tempfile.TemporaryDirectory() as base:
            mapping = {"PrimarySync": "Eric", "SharedLibrary": "Shared"}
            result = _library_destination(
                base, "SharedSync-3C977B4A-C15A-46E4-9854-585B9342C409", mapping,
            )
            assert result == os.path.join(base, "Shared")
            assert os.path.isdir(result)

    def test_shared_library_alias_only_fires_for_sharedsync_prefix(self):
        """The alias rule does NOT silently catch unrelated library names —
        a non-SharedSync library that isn't explicitly mapped still falls
        through to base."""
        with tempfile.TemporaryDirectory() as base:
            mapping = {"PrimarySync": "Eric", "SharedLibrary": "Shared"}
            result = _library_destination(base, "OtherLibrary", mapping)
            assert result == base

    def test_exact_match_wins_over_shared_library_alias(self):
        """If the exact GUID is mapped explicitly, that wins over the
        ``SharedLibrary`` alias — predictability for users who pinned the
        GUID before this feature shipped."""
        with tempfile.TemporaryDirectory() as base:
            guid_name = "SharedSync-DEADBEEF-1234-5678-9ABC-DEF012345678"
            mapping = {guid_name: "Exact", "SharedLibrary": "Aliased"}
            result = _library_destination(base, guid_name, mapping)
            assert result == os.path.join(base, "Exact")


class TestSyncPhotosRemoveObsoletePerLibrary(unittest.TestCase):
    """When ``library_destinations`` is configured AND
    ``photos.remove_obsolete`` is true, ``sync_photos`` must call the
    obsolete-cleanup once per library subdir (not once on the parent
    destination — that would walk siblings' photo trees and delete them)."""

    def test_per_library_remove_obsolete_invokes_once_per_subdir(self):
        from unittest.mock import MagicMock, patch

        from src import sync_photos as sp

        with tempfile.TemporaryDirectory() as base:
            config = {
                "photos": {
                    "destination": base,
                    "remove_obsolete": True,
                    "library_destinations": {
                        "PrimarySync": "personal",
                        "SharedLibrary": "shared",
                    },
                    "filters": {
                        "libraries": ["PrimarySync", "SharedLibrary"],
                        "file_sizes": ["original"],
                    },
                },
            }
            fake_photos = MagicMock()
            fake_photos.libraries = {
                "PrimarySync": MagicMock(),
                "SharedLibrary": MagicMock(),
            }

            with patch.object(
                sp.config_parser,
                "prepare_photos_destination",
                return_value=base,
            ), patch.object(
                sp,
                "_sync_albums_by_configuration",
                return_value=(0, 0),
            ), patch.object(
                sp, "remove_obsolete_files",
            ) as fake_remove:
                sp.sync_photos(config=config, photos=fake_photos)

            called_paths = [c.args[0] for c in fake_remove.call_args_list]
            assert called_paths == [
                os.path.join(base, "personal"),
                os.path.join(base, "shared"),
            ]
