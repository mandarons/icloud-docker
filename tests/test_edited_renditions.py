"""Tests for syncing edited photos (``full``) and the options around it.

The edit is ``resJPEGFull*`` on the ``CPLAsset`` record, surfaced by icloudpy
0.12.0 as the ``full`` version. ``original_alt`` is the RAW/JPEG pair
alternate and is not an edit. Shapes here follow icloudpy's recorded fixtures
(field names and the asset/master split); every id and value is synthetic.
"""

import unittest
from unittest.mock import MagicMock, Mock

from src import config_parser
from src.album_sync_orchestrator import _collect_photo_download_tasks
from src.photo_download_manager import (
    collect_download_task,
    set_fallback_to_original,
    would_fall_back_to_original,
)
from src.photo_file_utils import _refresh_photo_download_url
from src.photo_path_utils import (
    generate_photo_filename_with_metadata,
    get_photo_name_and_extension,
    photo_has_edit,
    set_adjusted_suffix,
    set_default_filename_format,
    set_file_format,
    set_preserve_originals_as_bak,
)


def _version(size=1234, mime="public.jpeg", url="https://cdn.invalid/x"):
    return {"size": size, "type": mime, "url": url}


def _photo(filename="IMG_1234.HEIC", photo_id="abc", versions=None):
    photo = MagicMock()
    photo.filename = filename
    photo.id = photo_id
    photo.created = None
    photo.versions = versions if versions is not None else {"original": _version()}
    return photo


class TestFileSizeAliases(unittest.TestCase):
    def test_adjusted_maps_to_full(self):
        assert config_parser.validate_file_sizes(["adjusted"]) == ["full"]

    def test_alternative_maps_to_original_alt(self):
        assert config_parser.validate_file_sizes(["alternative"]) == ["original_alt"]

    def test_aliases_and_canonical_forms_are_collapsed(self):
        """``adjusted`` and ``full`` are one download, not two."""
        assert config_parser.validate_file_sizes(
            ["original", "adjusted", "full"],
        ) == ["original", "full"]

    def test_unknown_value_is_dropped_when_something_valid_remains(self):
        assert config_parser.validate_file_sizes(["bogus", "adjusted"]) == ["full"]

    def test_only_unknown_values_fall_back_to_original(self):
        assert config_parser.validate_file_sizes(["bogus"]) == ["original"]


class TestFallbackConfig(unittest.TestCase):
    def test_default_is_false(self):
        assert config_parser.get_photos_fallback_to_original({}) is False

    def test_true_is_true(self):
        config = {"photos": {"filters": {"fallback_to_original": True}}}
        assert config_parser.get_photos_fallback_to_original(config) is True

    def test_truthy_value_normalised(self):
        config = {"photos": {"filters": {"fallback_to_original": "yes"}}}
        assert config_parser.get_photos_fallback_to_original(config) is True

    def test_parsed_filters_carry_the_value(self):
        config = {"photos": {"filters": {"fallback_to_original": True}}}
        assert config_parser.get_photos_filters(config)["fallback_to_original"] is True


class TestFallbackWhenSizeIsAbsent(unittest.TestCase):
    """``fallback_to_original`` substitutes ``original`` for an absent size."""

    def tearDown(self):
        set_fallback_to_original(False)

    def _collect(self, photo, file_size):
        return collect_download_task(
            photo, file_size, "/tmp/dest", None, None, None,
        )

    def test_absent_edit_falls_back_to_original(self):
        set_fallback_to_original(True)
        photo = _photo(versions={"original": _version(mime="public.heic")})
        task = self._collect(photo, "full")
        assert task is not None
        assert task.file_size == "original"
        assert task.photo_path.endswith(".HEIC")

    def test_absent_edit_is_skipped_when_fallback_is_off(self):
        set_fallback_to_original(False)
        photo = _photo()
        assert self._collect(photo, "full") is None

    def test_present_edit_is_downloaded_as_the_edit(self):
        set_fallback_to_original(True)
        photo = _photo(versions={"original": _version(), "full": _version(mime="public.jpeg")})
        task = self._collect(photo, "full")
        assert task is not None
        assert task.file_size == "full"

    def test_live_video_never_falls_back_to_the_still(self):
        """A still image under a .mov name is not a video."""
        set_fallback_to_original(True)
        photo = _photo()
        assert self._collect(photo, "live_video_original") is None

    def test_no_fallback_when_original_is_absent_too(self):
        set_fallback_to_original(True)
        photo = _photo(versions={"medium": _version()})
        assert self._collect(photo, "full") is None

    def test_original_request_itself_does_not_fall_back(self):
        set_fallback_to_original(True)
        photo = _photo(versions={"medium": _version()})
        assert self._collect(photo, "original") is None


class TestEditNaming(unittest.TestCase):
    def tearDown(self):
        set_adjusted_suffix(False)
        set_default_filename_format("metadata")
        set_file_format(None)

    def test_full_extension_comes_from_the_mime_type(self):
        """The edit is a JPEG even when the original is HEIC."""
        photo = _photo(versions={"original": _version(mime="public.heic"), "full": _version()})
        assert get_photo_name_and_extension(photo, "full") == ("IMG_1234", "jpeg")

    def test_unknown_mime_keeps_the_filename_extension(self):
        photo = _photo(
            versions={"original": _version(mime="public.heic"),
                      "full": _version(mime="public.unheard-of")},
        )
        assert get_photo_name_and_extension(photo, "full") == ("IMG_1234", "HEIC")

    def test_simple_mode_marks_the_edit_when_names_would_collide(self):
        set_default_filename_format("simple")
        set_adjusted_suffix(True)
        photo = _photo(
            filename="IMG_1234.jpeg",
            versions={"original": _version(), "full": _version()},
        )
        assert generate_photo_filename_with_metadata(photo, "original", "simple") == "IMG_1234.jpeg"
        assert (
            generate_photo_filename_with_metadata(photo, "full", "simple")
            == "IMG_1234-adjusted.jpeg"
        )

    def test_simple_mode_adds_no_marker_when_extensions_differ(self):
        set_default_filename_format("simple")
        set_adjusted_suffix(True)
        photo = _photo(
            filename="IMG_1234.HEIC",
            versions={"original": _version(mime="public.heic"), "full": _version()},
        )
        assert generate_photo_filename_with_metadata(photo, "full", "simple") == "IMG_1234.jpeg"

    def test_simple_mode_adds_no_marker_when_the_original_is_not_requested(self):
        set_default_filename_format("simple")
        set_adjusted_suffix(False)
        photo = _photo(
            filename="IMG_1234.jpeg",
            versions={"original": _version(), "full": _version()},
        )
        assert generate_photo_filename_with_metadata(photo, "full", "simple") == "IMG_1234.jpeg"

    def test_metadata_mode_stays_unique(self):
        set_adjusted_suffix(True)
        photo = _photo(
            filename="IMG_1234.jpeg",
            versions={"original": _version(), "full": _version()},
        )
        name = generate_photo_filename_with_metadata(photo, "full", "metadata")
        assert "__full__" in name
        assert name.endswith(".jpeg")

    def test_template_treats_full_as_a_variant_when_original_is_requested(self):
        set_file_format("${photo.filename}${photo.variant_suffix}.${photo.ext}")
        set_adjusted_suffix(True)
        photo = _photo(
            filename="IMG_1234.HEIC",
            versions={"original": _version(mime="public.heic"), "full": _version()},
        )
        assert (
            generate_photo_filename_with_metadata(photo, "original")
            == "IMG_1234.HEIC"
        )
        assert generate_photo_filename_with_metadata(photo, "full") == "IMG_1234_full.jpeg"

    def test_template_keeps_full_primary_when_it_is_the_only_copy(self):
        set_file_format("${photo.filename}${photo.variant_suffix}.${photo.ext}")
        set_adjusted_suffix(False)
        photo = _photo(versions={"original": _version(mime="public.heic"), "full": _version()})
        assert generate_photo_filename_with_metadata(photo, "full") == "IMG_1234.jpeg"


class TestSyncWiring(unittest.TestCase):
    """``sync_photos`` wires the module-level switches from the parsed config."""

    def tearDown(self):
        set_adjusted_suffix(False)
        set_fallback_to_original(False)

    def _run(self, file_sizes, fallback):
        from unittest.mock import patch

        from src import sync_photos

        config = {
            "photos": {
                "destination": "photos",
                "filters": {
                    "libraries": ["PrimarySync"],
                    "file_sizes": file_sizes,
                    "fallback_to_original": fallback,
                },
            },
        }
        api_photos = MagicMock()
        api_photos.libraries = {"PrimarySync": MagicMock(all=[], albums={})}
        with patch.object(
            sync_photos.config_parser, "prepare_photos_destination", return_value="/tmp/photos",
        ), patch.object(
            sync_photos, "_sync_albums_by_configuration", return_value=(0, 0),
        ), patch.object(
            sync_photos, "remove_obsolete_files",
        ), patch(
            "src.photo_download_manager.set_fallback_to_original",
        ) as fake_fallback, patch(
            "src.photo_path_utils.set_adjusted_suffix",
        ) as fake_suffix:
            sync_photos.sync_photos(config=config, photos=api_photos)
        return fake_fallback, fake_suffix

    def test_fallback_is_enabled_when_only_the_edit_is_requested(self):
        fake_fallback, _ = self._run(["full"], fallback=True)
        fake_fallback.assert_called_once_with(True)

    def test_fallback_is_disabled_when_original_is_already_requested(self):
        """Otherwise an unedited photo queues the same path twice and races."""
        fake_fallback, _ = self._run(["original", "full"], fallback=True)
        fake_fallback.assert_called_once_with(False)

    def test_fallback_is_disabled_when_the_option_is_off(self):
        fake_fallback, _ = self._run(["full"], fallback=False)
        fake_fallback.assert_called_once_with(False)

    def test_the_edit_is_marked_only_when_both_copies_are_requested(self):
        _, suffix_both = self._run(["original", "full"], fallback=False)
        suffix_both.assert_called_once_with(True)
        _, suffix_edit_only = self._run(["full"], fallback=False)
        suffix_edit_only.assert_called_once_with(False)


def _photo_with_asset(fields=None, versions=None, filename="IMG_1234.HEIC"):
    """Photo whose ``CPLAsset`` record is an explicit dict, as icloudpy builds it."""
    photo = _photo(filename=filename, versions=versions)
    photo._asset_record = {  # noqa: SLF001 - the record icloudpy attaches to the asset
        "recordName": "asset-1",
        "recordType": "CPLAsset",
        "fields": fields if fields is not None else {},
    }
    return photo


class TestEditDetection(unittest.TestCase):
    """``full`` is an edit only when the ``CPLAsset`` record carries it."""

    def test_asset_record_still_edit_is_an_edit(self):
        photo = _photo_with_asset({"resJPEGFullRes": {"value": {}}})
        assert photo_has_edit(photo) is True

    def test_asset_record_video_edit_is_an_edit(self):
        photo = _photo_with_asset({"resVidFullRes": {"value": {}}})
        assert photo_has_edit(photo) is True

    def test_master_carried_full_is_not_an_edit(self):
        """A master ``full`` is Apple's display render for PNG/RAW/GIF."""
        photo = _photo_with_asset(
            {"resOriginalRes": {"value": {}}},
            versions={"original": _version(mime="public.png"), "full": _version()},
        )
        assert photo_has_edit(photo) is False

    def test_empty_asset_record_is_not_an_edit(self):
        photo = _photo_with_asset(
            {}, versions={"original": _version(), "full": _version()},
        )
        assert photo_has_edit(photo) is False

    def test_object_without_a_dict_asset_record_keeps_the_versions_answer(self):
        photo = _photo(versions={"original": _version(), "full": _version()})
        assert photo_has_edit(photo) is True

    def test_unreadable_versions_is_no_edit(self):
        class Broken:
            @property
            def versions(self):
                msg = "partial record"
                raise RuntimeError(msg)

        assert photo_has_edit(Broken()) is False


class TestMasterCarriedFullIsNotAnEdit(unittest.TestCase):
    """A display render must not be downloaded or hide the real original."""

    def setUp(self):
        self.photo = _photo_with_asset(
            {"resOriginalRes": {"value": {}}},
            versions={"original": _version(mime="public.png"), "full": _version()},
            filename="IMG_5678.PNG",
        )

    def tearDown(self):
        set_fallback_to_original(False)
        set_preserve_originals_as_bak(False)

    def test_skipped_when_fallback_is_off(self):
        set_fallback_to_original(False)
        assert self._collect("full") is None

    def test_falls_back_to_the_true_original(self):
        set_fallback_to_original(True)
        task = self._collect("full")
        assert task is not None
        assert task.file_size == "original"
        assert task.photo_path.endswith(".PNG")

    def test_original_is_not_hidden_as_bak(self):
        set_preserve_originals_as_bak(True)
        assert generate_photo_filename_with_metadata(
            self.photo, "original", "simple",
        ) == "IMG_5678.PNG"

    def test_a_genuine_edit_is_still_hidden(self):
        set_preserve_originals_as_bak(True)
        edited = _photo_with_asset(
            {"resJPEGFullRes": {"value": {}}},
            versions={"original": _version(mime="public.png"), "full": _version()},
            filename="IMG_5678.PNG",
        )
        assert generate_photo_filename_with_metadata(
            edited, "original", "simple",
        ) == "IMG_5678.PNG.original.bak"

    def _collect(self, file_size):
        return collect_download_task(self.photo, file_size, "/tmp/dest", None, None, None)


class TestFallbackClaimsOneOriginalPerPhoto(unittest.TestCase):
    """Two absent sizes must not resolve to the same ``original`` path."""

    def tearDown(self):
        set_fallback_to_original(False)
        set_default_filename_format("metadata")

    def _tasks(self, photo, file_sizes):
        return _collect_photo_download_tasks(
            photo, "/tmp/dest", file_sizes, None, None, None, None,
        )

    def test_two_absent_sizes_queue_the_original_once(self):
        set_fallback_to_original(True)
        photo = _photo(versions={"original": _version(mime="public.heic")})
        tasks = self._tasks(photo, ["full", "original_alt"])
        assert len(tasks) == 1
        assert tasks[0].file_size == "original"

    def test_simple_mode_keeps_one_copy_per_photo(self):
        set_fallback_to_original(True)
        set_default_filename_format("simple")
        photo = _photo(
            filename="IMG_1234.HEIC",
            versions={"original": _version(mime="public.heic")},
        )
        tasks = self._tasks(photo, ["full", "original_alt"])
        assert [task.photo_path for task in tasks] == ["/tmp/dest/IMG_1234.HEIC"]

    def test_an_edited_photo_still_gets_the_edit_and_the_original(self):
        set_fallback_to_original(True)
        photo = _photo(
            versions={
                "original": _version(mime="public.heic"),
                "full": _version(mime="public.heic"),
            },
        )
        tasks = self._tasks(photo, ["full", "original_alt"])
        assert len(tasks) == 2
        assert sorted(task.file_size for task in tasks) == ["full", "original"]

    def test_predicate_matches_the_collector(self):
        set_fallback_to_original(True)
        photo = _photo(versions={"original": _version()})
        assert would_fall_back_to_original(photo, "full") is True
        assert would_fall_back_to_original(photo, "original") is False


class TestEditedVideoAndJpegNaming(unittest.TestCase):
    def tearDown(self):
        set_adjusted_suffix(False)
        set_default_filename_format("metadata")

    def test_edited_video_uses_the_video_container(self):
        photo = _photo(
            filename="CLIP.AVI",
            versions={
                "original": _version(mime="public.avi"),
                "full": _version(mime="public.mpeg-4"),
            },
        )
        assert get_photo_name_and_extension(photo, "full") == ("CLIP", "MP4")

    def test_edited_quicktime_video_uses_mov(self):
        photo = _photo(
            filename="CLIP.AVI",
            versions={
                "original": _version(mime="public.avi"),
                "full": _version(mime="com.apple.quicktime-movie"),
            },
        )
        assert get_photo_name_and_extension(photo, "full") == ("CLIP", "MOV")

    def test_original_alt_never_uses_the_video_mapping(self):
        photo = _photo(
            filename="CLIP.AVI",
            versions={
                "original": _version(mime="public.avi"),
                "original_alt": _version(mime="com.apple.quicktime-movie"),
            },
        )
        assert get_photo_name_and_extension(photo, "original_alt") == ("CLIP", "AVI")

    def test_jpg_and_jpeg_count_as_one_container_for_the_marker(self):
        set_default_filename_format("simple")
        set_adjusted_suffix(True)
        photo = _photo(
            filename="IMG_1234.JPG",
            versions={"original": _version(), "full": _version()},
        )
        assert generate_photo_filename_with_metadata(
            photo, "full", "simple",
        ) == "IMG_1234-adjusted.jpeg"


def _refresh_photo(record_names, asset_fields=None, versions=None):
    master_name, asset_name = record_names
    master = {
        "recordName": master_name,
        "recordType": "CPLMaster",
        "fields": {"resOriginalRes": {"value": {"size": 1, "downloadURL": "https://old"}}},
        "zoneID": {"zoneName": "PrimarySync"},
    }
    asset = {
        "recordName": asset_name,
        "recordType": "CPLAsset",
        "fields": asset_fields or {},
        "zoneID": {"zoneName": "PrimarySync"},
    }
    service = Mock()
    service._service_endpoint = "https://cv.icloud.com"  # noqa: SLF001
    service.zone_id = {"zoneName": "PrimarySync"}
    service.params = {"auth": "token"}
    photo = Mock()
    photo._master_record = master  # noqa: SLF001
    photo._asset_record = asset  # noqa: SLF001
    photo._service = service  # noqa: SLF001
    photo._versions = versions if versions is not None else {"original": {}}  # noqa: SLF001
    return photo, service


def _respond(service, records):
    response = MagicMock()
    response.json.return_value = {"records": records}
    service.session.post.return_value = response


def _fresh(record):
    return {**record, "recordName": record["recordName"], "fields": {"resJPEGFullRes": {
        "value": {"size": 2, "downloadURL": "https://fresh"},
    }}}


class TestExpiredUrlRefreshCoversTheAssetRecord(unittest.TestCase):
    """The edit's URL lives on CPLAsset, whose recordName differs from the master's."""

    def test_both_records_are_requested_and_updated(self):
        photo, service = _refresh_photo(
            ("M-1", "A-1"),
            asset_fields={"resJPEGFullRes": {"value": {"size": 2, "downloadURL": "https://old"}}},
        )
        master_fresh = _fresh(photo._master_record)  # noqa: SLF001
        asset_fresh = _fresh(photo._asset_record)  # noqa: SLF001
        _respond(service, [master_fresh, asset_fresh])

        assert _refresh_photo_download_url(photo) is True

        query = service.session.post.call_args[1]["data"]
        import json

        names = [r["recordName"] for r in json.loads(query)["records"]]
        assert names == ["M-1", "A-1"]
        assert photo._master_record is master_fresh  # noqa: SLF001
        assert photo._asset_record is asset_fresh  # noqa: SLF001
        assert photo._versions is None  # noqa: SLF001

    def test_unedited_photo_only_looks_up_the_master(self):
        photo, service = _refresh_photo(("M-2", "A-2"), asset_fields={"assetDate": {"value": 1}})
        _respond(service, [_fresh(photo._master_record)])  # noqa: SLF001

        assert _refresh_photo_download_url(photo) is True

        import json

        query = service.session.post.call_args[1]["data"]
        assert [r["recordName"] for r in json.loads(query)["records"]] == ["M-2"]

    def test_an_edited_photo_whose_asset_refresh_fails_is_not_reported_success(self):
        photo, service = _refresh_photo(
            ("M-3", "A-3"),
            asset_fields={"resJPEGFullRes": {"value": {"size": 1, "downloadURL": "https://old"}}},
        )
        _respond(service, [
            _fresh(photo._master_record),  # noqa: SLF001
            {"recordName": "A-3", "serverErrorCode": "NOT_FOUND", "reason": "gone"},
        ])

        assert _refresh_photo_download_url(photo) is False
        # Nothing was replaced, so the retry still has usable (if stale) data.
        assert photo._versions == {"original": {}}  # noqa: SLF001

    def test_master_error_payload_is_reported_not_treated_as_fresh(self):
        photo, service = _refresh_photo(("M-4", "A-4"))
        _respond(service, [
            {"recordName": "M-4", "serverErrorCode": "NOT_FOUND", "reason": "gone"},
        ])

        assert _refresh_photo_download_url(photo) is False
        assert photo._master_record["recordName"] == "M-4"  # noqa: SLF001

    def test_a_record_shared_between_master_and_asset_is_requested_once(self):
        photo, service = _refresh_photo(("SAME", "SAME"),
                                        asset_fields={"resJPEGFullRes": {"value": {}}})
        _respond(service, [_fresh(photo._master_record)])  # noqa: SLF001

        assert _refresh_photo_download_url(photo) is True
        import json

        query = service.session.post.call_args[1]["data"]
        assert [r["recordName"] for r in json.loads(query)["records"]] == ["SAME"]
