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
            }
        }
        result = config_parser.get_photos_library_destinations(config)
        assert result == {"PrimarySync": "personal", "SharedLibrary": "shared"}

    def test_returns_empty_dict_when_value_is_not_a_dict(self):
        config = {"photos": {"library_destinations": ["foo", "bar"]}}
        assert config_parser.get_photos_library_destinations(config) == {}

    def test_coerces_non_string_keys_and_values_to_str(self):
        config = {
            "photos": {"library_destinations": {123: 456, "PrimarySync": "personal"}}
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
