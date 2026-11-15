"""Tests for recognising another tool's photo tree in place (``photos.adopt``).

Covers the config switches (``photos.all_folder``, ``photos.adopt``), the
icloudpd name matcher (``photo_adopt.Adopter``) and its hook in the
download decision. Helpers here are shared with ``test_member_sync``.
"""

import datetime
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import src
import tests  # noqa: F401 - sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import config_parser, photo_adopt, photo_download_manager, sync_photos
from src.photo_path_utils import set_default_filename_format

MAIN = "main@example.com"
MEMBER = "member@example.com"
UTC = datetime.UTC


def _config(root, entry=None, photos=None):
    photos = (
        photos
        if photos is not None
        else {
            "destination": "photos",
            "library_destinations": {"PrimarySync": "Main", "SharedSync": "Shared"},
            "filename_format": "simple",
            "remove_obsolete": True,
            "all_albums": True,
            "filters": {
                "albums": ["Trip"],
                "file_sizes": ["original", "live_video_original"],
            },
            "sync_interval": 600,
        }
    )
    config = {
        "app": {
            "root": root,
            "credentials": {"username": MAIN, "retry_login_interval": 600},
        },
        "drive": {"destination": "drive"},
        "photos": photos,
        "accounts": [entry or {"id": "member"}],
    }
    return config


def _photo(filename, size, created=None, video_size=None, record="rec"):
    photo = MagicMock()
    photo.filename = filename
    photo.id = record
    photo.versions = {"original": {"type": "public.heic", "size": size}}
    if video_size is not None:
        photo.versions["live_video_original"] = {
            "type": "com.apple.quicktime-movie",
            "size": video_size,
        }
    photo.created = created or datetime.datetime(2024, 5, 3, 2, 0, tzinfo=UTC)
    return photo


def _write(path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)
    return path


class _Dirs(unittest.TestCase):
    """A config folder and a photo root of its own for every test."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.addCleanup(shutil.rmtree, self.root, True)
        env = patch.dict(os.environ, {"ICLOUD_DOCKER_CONFIG_DIR": self.dir})
        env.start()
        self.addCleanup(env.stop)
        cookie = patch.object(src, "DEFAULT_COOKIE_DIRECTORY", os.path.join(self.dir, "session_data"))
        cookie.start()
        self.addCleanup(cookie.stop)
        set_default_filename_format("simple")
        self.addCleanup(set_default_filename_format, "metadata")


class TestConfigGetters(unittest.TestCase):
    def test_all_folder(self):
        self.assertEqual(config_parser.get_photos_all_folder({"photos": {}}), "all")
        self.assertEqual(config_parser.get_photos_all_folder({"photos": {"all_folder": ""}}), "")
        self.assertEqual(
            config_parser.get_photos_all_folder({"photos": {"all_folder": "/Everything/"}}),
            "Everything",
        )
        self.assertEqual(config_parser.get_photos_all_folder({"photos": {"all_folder": ".."}}), "all")

    def test_adopt(self):
        self.assertIsNone(config_parser.get_photos_adopt({"photos": {}}))
        self.assertIsNone(config_parser.get_photos_adopt({"photos": {"adopt": False}}))
        self.assertEqual(
            config_parser.get_photos_adopt({"photos": {"adopt": " ICloudPD "}}),
            "icloudpd",
        )
        self.assertIsNone(config_parser.get_photos_adopt({"photos": {"adopt": "osxphotos"}}))


class TestAdopter(_Dirs):
    def setUp(self):
        super().setUp()
        self.base = os.path.join(self.root, "Member")
        self.adopter = photo_adopt.Adopter()

    def _day(self, day="03"):
        return os.path.join(self.base, "2024", "05", day)

    def test_icloudpd_names(self):
        cases = [
            ("IMG_1.HEIC", "original", "IMG_1.HEIC"),
            ("IMG_2.HEIC", "original", "IMG_2-100.HEIC"),
            ("IMG_3.HEIC", "original", "img_3.heic"),
            ("IMG_4.HEIC", "live_video_original", "IMG_4_HEVC.MOV"),
            ("IMG_5.HEIC", "live_video_original", "IMG_5_HEVC-200.MOV"),
            ("IMG_6.JPG", "live_video_original", "IMG_6.mov"),
        ]
        for filename, size_name, on_disk in cases:
            with self.subTest(on_disk=on_disk):
                size = 200 if size_name.startswith("live") else 100
                path = _write(os.path.join(self._day(), on_disk), size)
                photo = _photo(filename, 100, video_size=200)
                adopter = photo_adopt.Adopter()
                self.assertEqual(adopter.find(photo, size_name, self.base, "%Y/%m/%d"), path)

    def test_neighbouring_day(self):
        path = _write(os.path.join(self._day("02"), "IMG_1.HEIC"), 100)
        self.assertEqual(
            self.adopter.find(_photo("IMG_1.HEIC", 100), "original", self.base, "%Y/%m/%d"),
            path,
        )

    def test_refuses_wrong_size_claimed_and_far_days(self):
        _write(os.path.join(self._day(), "IMG_1.HEIC"), 99)
        claimed = _write(os.path.join(self._day(), "IMG_1-100.HEIC"), 100)
        _write(os.path.join(self._day("06"), "IMG_1.HEIC"), 100)
        photo = _photo("IMG_1.HEIC", 100)
        self.assertIsNone(self.adopter.find(photo, "original", self.base, "%Y/%m/%d", claimed={claimed}))

    def test_suffix_must_be_the_size(self):
        _write(os.path.join(self._day(), "IMG_1-123.HEIC"), 100)
        self.assertIsNone(self.adopter.find(_photo("IMG_1.HEIC", 100), "original", self.base, "%Y/%m/%d"))

    def test_without_folder_format(self):
        path = _write(os.path.join(self.base, "IMG_1-100.HEIC"), 100)
        self.assertEqual(
            self.adopter.find(_photo("IMG_1.HEIC", 100), "original", self.base, None),
            path,
        )

    def test_odd_photos(self):
        photo = _photo("IMG_1.HEIC", 100)
        self.assertIsNone(self.adopter.find(photo, "medium", self.base, "%Y/%m/%d"))
        photo.created = None
        self.assertIsNone(self.adopter.find(photo, "original", self.base, "%Y/%m/%d"))
        # A date that cannot move a day either way still checks its own day.
        photo.created = datetime.datetime.max.replace(tzinfo=UTC)
        self.assertIsNone(self.adopter.find(photo, "original", self.base, "%Y/%m/%d"))

    def test_unreadable_candidate(self):
        path = _write(os.path.join(self._day(), "IMG_1.HEIC"), 100)
        with patch("os.path.getsize", side_effect=OSError):
            self.assertIsNone(self.adopter.find(_photo("IMG_1.HEIC", 100), "original", self.base, "%Y/%m/%d"))
        self.assertTrue(os.path.isfile(path))

    def test_listing_is_read_once(self):
        _write(os.path.join(self._day(), "IMG_1.HEIC"), 100)
        with patch("os.listdir", wraps=os.listdir) as listdir:
            for _ in range(3):
                self.adopter.find(_photo("IMG_9.HEIC", 100), "original", self.base, "%Y/%m/%d")
        self.assertEqual(listdir.call_count, 3)  # three day folders, once each


class TestCollectWithAdopter(_Dirs):
    def setUp(self):
        super().setUp()
        self.base = os.path.join(self.root, "Member")

    def _collect(self, photo, files, size_name="original"):
        return photo_download_manager.collect_download_task(photo, size_name, self.base, files, "%Y/%m/%d", None)

    def test_old_name_is_tracked_and_nothing_created(self):
        old = _write(os.path.join(self.base, "2024", "05", "02", "IMG_1_HEVC.MOV"), 200)
        files = set()
        token = photo_adopt.ADOPTER.set(photo_adopt.Adopter())
        try:
            self.assertIsNone(
                self._collect(
                    _photo("IMG_1.HEIC", 100, video_size=200),
                    files,
                    "live_video_original",
                ),
            )
            self.assertEqual(photo_adopt.ADOPTER.get().adopted, 1)
        finally:
            photo_adopt.ADOPTER.reset(token)
        self.assertEqual(files, {old})
        self.assertFalse(os.path.exists(os.path.join(self.base, "2024", "05", "03")))

    def test_expected_file_wins(self):
        expected = _write(os.path.join(self.base, "2024", "05", "03", "IMG_1.HEIC"), 100)
        token = photo_adopt.ADOPTER.set(photo_adopt.Adopter())
        try:
            files = set()
            self.assertIsNone(self._collect(_photo("IMG_1.HEIC", 100), files))
            self.assertEqual(photo_adopt.ADOPTER.get().adopted, 0)
            self.assertIn(expected, files)
            # Nothing anywhere: a normal download, and no files set is fine.
            self.assertIsNotNone(self._collect(_photo("IMG_2.HEIC", 100), None))
        finally:
            photo_adopt.ADOPTER.reset(token)

    def test_adopted_without_a_files_set(self):
        _write(os.path.join(self.base, "2024", "05", "03", "IMG_1-100.HEIC"), 100)
        token = photo_adopt.ADOPTER.set(photo_adopt.Adopter())
        try:
            self.assertIsNone(self._collect(_photo("IMG_1.HEIC", 100), None))
        finally:
            photo_adopt.ADOPTER.reset(token)

    def test_off_by_default(self):
        _write(os.path.join(self.base, "2024", "05", "03", "IMG_1-100.HEIC"), 100)
        self.assertIsNotNone(self._collect(_photo("IMG_1.HEIC", 100), set()))


class TestAllFolder(_Dirs):
    def test_tree_straight_under_the_library(self):
        photos = MagicMock()
        with patch.object(sync_photos, "sync_album_photos", return_value=(1, 0)) as album:
            for value, expected in (("", "lib"), ("all", os.path.join("lib", "all"))):
                result = sync_photos._sync_all_photos_in_library(  # noqa: SLF001
                    photos,
                    "PrimarySync",
                    "lib",
                    {"file_sizes": [], "extensions": None},
                    set(),
                    None,
                    None,
                    {"photos": {"all_folder": value}},
                )
                self.assertEqual(result, (1, 0))
                self.assertEqual(album.call_args.kwargs["destination_path"], expected)
