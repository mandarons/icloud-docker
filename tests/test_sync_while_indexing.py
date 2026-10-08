"""Photos keeps syncing while Apple reports a library still indexing.

Apple can report a library as indexing for weeks while listing it in full.
Refusing to open Photos until it finishes backs up nothing in the meantime,
so the library is opened, synced, and kept out of obsolete-file cleanup --
an incomplete listing would otherwise read as deletions.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import tests  # noqa: F401  — env setup
from src import sync, sync_photos


def _library(state=None):
    library = MagicMock()
    if state is not None:
        library.indexing_state = state
    else:
        del library.indexing_state
    return library


class TestPhotosOpensWhileIndexing(unittest.TestCase):
    def test_the_client_is_asked_to_open_unfinished_libraries(self):
        for region in ("global", "china"):
            with (
                self.subTest(region=region),
                patch.object(sync, "ICloudPyService") as client,
            ):
                sync.get_api_instance(
                    "a@icloud.com", "pw", cookie_directory="session", server_region=region,
                )
            self.assertIs(
                client.call_args.kwargs["photos_require_finished_index"], False,
            )


class TestLibrariesStillIndexing(unittest.TestCase):
    def _indexing(self, libraries, wanted=None):
        photos = MagicMock()
        photos.libraries = libraries
        return sync_photos._libraries_still_indexing(  # noqa: SLF001
            photos, wanted or list(libraries),
        )

    def test_only_unfinished_libraries_are_reported(self):
        libraries = {
            "PrimarySync": _library("FINISHED"),
            "SharedSync-1": _library("RUNNING"),
        }
        with self.assertLogs(level="WARNING") as logs:
            self.assertEqual(self._indexing(libraries), {"SharedSync-1"})
        self.assertIn("still indexing SharedSync-1 (RUNNING)", "\n".join(logs.output))

    def test_a_library_without_a_state_is_finished(self):
        """An icloudpy that records no state refuses unfinished libraries."""
        self.assertEqual(self._indexing({"PrimarySync": _library()}), set())

    def test_a_library_not_being_synced_is_ignored(self):
        libraries = {
            "PrimarySync": _library("FINISHED"),
            "SharedSync-1": _library("RUNNING"),
        }
        self.assertEqual(self._indexing(libraries, wanted=["PrimarySync"]), set())

    def test_a_configured_library_that_does_not_exist_is_ignored(self):
        self.assertEqual(self._indexing({}, wanted=["Missing"]), set())

    def test_libraries_that_cannot_be_listed_are_left_to_the_sync(self):
        from icloudpy import exceptions

        photos = MagicMock()
        type(photos).libraries = property(
            lambda _self: (_ for _ in ()).throw(
                exceptions.ICloudPyAPIResponseException("down", 503),
            ),
        )
        self.assertEqual(
            sync_photos._libraries_still_indexing(photos, ["PrimarySync"]), set(),  # noqa: SLF001
        )


class TestCleanupWaitsForTheIndex(unittest.TestCase):
    """The library is synced either way; only its cleanup waits."""

    def _clean(self, states, library_destinations=None):
        with tempfile.TemporaryDirectory() as base:
            config = {
                "photos": {
                    "destination": base,
                    "remove_obsolete": True,
                    "filters": {"libraries": list(states), "file_sizes": ["original"]},
                },
            }
            if library_destinations:
                config["photos"]["library_destinations"] = library_destinations
            photos = MagicMock()
            photos.libraries = {name: _library(state) for name, state in states.items()}
            with (
                patch.object(
                    sync_photos.config_parser,
                    "prepare_photos_destination",
                    return_value=base,
                ),
                patch.object(
                    sync_photos, "_sync_albums_by_configuration", return_value=(0, 0),
                ) as synced,
                patch.object(sync_photos, "remove_obsolete_files") as removed,
            ):
                sync_photos.sync_photos(config=config, photos=photos)
            synced.assert_called_once()
            return [
                os.path.relpath(call.args[0], base) for call in removed.call_args_list
            ]

    def test_per_library_destinations_clean_only_finished_libraries(self):
        cleaned = self._clean(
            {"PrimarySync": "FINISHED", "SharedLibrary": "RUNNING"},
            library_destinations={"PrimarySync": "personal", "SharedLibrary": "shared"},
        )
        self.assertEqual(cleaned, ["personal"])

    def test_a_shared_destination_is_not_cleaned_while_any_library_indexes(self):
        self.assertEqual(
            self._clean({"PrimarySync": "FINISHED", "SharedLibrary": "RUNNING"}), [],
        )

    def test_a_shared_destination_is_cleaned_once_every_index_finishes(self):
        self.assertEqual(
            self._clean({"PrimarySync": "FINISHED", "SharedLibrary": "FINISHED"}), ["."],
        )
