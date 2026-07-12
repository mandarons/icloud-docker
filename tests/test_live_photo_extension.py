"""Tests for the Live Photo paired-video extension.

The live_video_* versions are QuickTime/MP4 movies; they must be written with
the real container extension (not the still's .HEIC), and an existing .HEIC
video from an earlier build must be renamed in place rather than re-downloaded.
"""

import os
import types

from src.photo_download_manager import generate_photo_path
from src.photo_path_utils import (
    generate_photo_filename_with_metadata,
    get_photo_name_and_extension,
)

_FTYP_QUICKTIME = b"\x00\x00\x00\x18ftypqt  \x00\x00\x02\x00qt  "


def _photo(filename, versions):
    """Minimal stand-in for an iCloudPy PhotoAsset."""
    return types.SimpleNamespace(filename=filename, versions=versions, id="ASSET-ID-1")


class TestLivePhotoExtension:
    def test_live_video_original_maps_to_mov(self):
        photo = _photo(
            "IMG_1234.HEIC",
            {
                "original": {"type": "public.heic"},
                "live_video_original": {"type": "com.apple.quicktime-movie"},
            },
        )
        name, ext = get_photo_name_and_extension(photo, "live_video_original")
        assert name == "IMG_1234"
        assert ext == "MOV"

    def test_live_video_unknown_type_defaults_to_mov(self):
        photo = _photo("IMG_1.HEIC", {"live_video_original": {"type": None}})
        assert get_photo_name_and_extension(photo, "live_video_original")[1] == "MOV"

    def test_live_video_mp4_type_maps_to_mp4(self):
        photo = _photo("IMG_1.HEIC", {"live_video_original": {"type": "public.mpeg-4"}})
        assert get_photo_name_and_extension(photo, "live_video_original")[1] == "MP4"

    def test_live_video_medium_and_thumb_are_mov(self):
        photo = _photo(
            "IMG_2.JPG",
            {
                "live_video_medium": {"type": "com.apple.quicktime-movie"},
                "live_video_thumb": {"type": "com.apple.quicktime-movie"},
            },
        )
        assert get_photo_name_and_extension(photo, "live_video_medium")[1] == "MOV"
        assert get_photo_name_and_extension(photo, "live_video_thumb")[1] == "MOV"

    def test_still_original_keeps_its_extension(self):
        photo = _photo("IMG_1234.HEIC", {"original": {"type": "public.heic"}})
        assert get_photo_name_and_extension(photo, "original")[1] == "HEIC"

    def test_filename_with_metadata_ends_in_mov(self):
        photo = _photo("IMG_9.HEIC", {"live_video_original": {"type": "com.apple.quicktime-movie"}})
        filename = generate_photo_filename_with_metadata(photo, "live_video_original")
        assert filename.endswith(".MOV")
        assert "__live_video_original__" in filename


class TestDownloadSelfHeal:
    def test_generate_photo_path_renames_legacy_heic_video(self, tmp_path):
        # An existing IMG__live_video_original__<id>.HEIC (from an earlier build)
        # must be renamed in place to the corrected .MOV, not left for re-download.
        photo = _photo("IMG_1.HEIC", {"live_video_original": {"type": "com.apple.quicktime-movie"}})
        corrected = generate_photo_filename_with_metadata(photo, "live_video_original")
        assert corrected.endswith(".MOV")
        legacy = os.path.join(str(tmp_path), corrected[: -len(".MOV")] + ".HEIC")
        with open(legacy, "wb") as handle:
            handle.write(_FTYP_QUICKTIME)

        result = generate_photo_path(photo, "live_video_original", str(tmp_path), None)

        assert result == os.path.join(str(tmp_path), corrected)
        assert os.path.exists(result)
        assert not os.path.exists(legacy)

    def test_generate_photo_path_no_legacy_is_noop(self, tmp_path):
        photo = _photo("IMG_2.HEIC", {"live_video_original": {"type": "com.apple.quicktime-movie"}})
        result = generate_photo_path(photo, "live_video_original", str(tmp_path), None)
        assert result.endswith(".MOV")
        assert not os.path.exists(result)
