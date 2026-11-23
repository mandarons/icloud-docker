"""Tests for a member's day folders in local time, deletes that follow
iCloud, and where the household page says the Shared Library lives."""

import contextvars
import datetime
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import tests  # noqa: F401 - sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import accounts, config_parser, member_report, photo_adopt, sync_photos, web, web_signals
from src.photo_path_utils import FOLDER_TZ, folder_date, resolve_folder_path
from tests.test_photo_adopt import MEMBER, UTC, _config, _Dirs, _photo, _write

# 02:00 UTC on the 3rd is the evening of the 2nd in California.
EVENING = datetime.datetime(2024, 5, 3, 2, 0, tzinfo=UTC)


def _in_zone(zone, fn, *args):
    """Run ``fn`` with FOLDER_TZ set, leaving this thread's value alone."""

    def run():
        FOLDER_TZ.set(zone)
        return fn(*args)

    return contextvars.copy_context().run(run)


class TestFolderTimezone(unittest.TestCase):
    def test_setting(self):
        for value, expected in (
            (None, None),
            ("", None),
            (False, None),
            ("local", "local"),
            (" Local ", "local"),
            ("America/Los_Angeles", "America/Los_Angeles"),
            ("Mars/Olympus", None),
            ("../etc", None),
        ):
            photos = {} if value is None else {"folder_timezone": value}
            self.assertEqual(config_parser.get_photos_folder_timezone({"photos": photos}), expected, value)

    def test_folder_named_in_the_zone(self):
        photo = _photo("IMG_1.HEIC", 1, created=EVENING)
        self.assertEqual(resolve_folder_path("b", "%Y/%m/%d", photo), os.path.join("b", "2024/05/03"))
        self.assertEqual(
            _in_zone("America/Los_Angeles", resolve_folder_path, "b", "%Y/%m/%d", photo),
            os.path.join("b", "2024/05/02"),
        )
        self.assertIs(folder_date(photo), EVENING)

    def test_local_is_the_containers_tz(self):
        photo = _photo("IMG_1.HEIC", 1, created=EVENING)
        with patch.dict(os.environ, {"TZ": "America/Los_Angeles"}):
            time.tzset()
            try:
                self.assertEqual(_in_zone("local", folder_date, photo).day, 2)
            finally:
                os.environ.pop("TZ")
                time.tzset()
        time.tzset()

    def test_each_pass_keeps_its_own_zone(self):
        """A member's pass on its own thread never changes the main account's folders."""
        seen = []

        def member_pass():
            sync_photos.apply_naming_settings({"photos": {"folder_timezone": "America/Los_Angeles"}})
            seen.append(FOLDER_TZ.get())

        thread = threading.Thread(target=member_pass)
        thread.start()
        thread.join()
        self.assertEqual(seen, ["America/Los_Angeles"])
        self.assertIsNone(FOLDER_TZ.get())


class TestOldTree(_Dirs):
    def test_old_tree_in_utc_days_is_still_found(self):
        """Neighbouring days are taken in the same zone as the expected one."""
        path = _write(os.path.join(self.root, "2024", "05", "03", "IMG_1.HEIC"), 7)
        found = _in_zone(
            "America/Los_Angeles",
            photo_adopt.Adopter().find,
            _photo("IMG_1.HEIC", 7, created=EVENING),
            "original",
            self.root,
            "%Y/%m/%d",
        )
        self.assertEqual(found, path)


class _Album(list):
    title = "All Photos"
    subalbums = ()


class _Library:
    indexing_state = "FINISHED"

    def __init__(self, photos):
        self.all = _Album(photos)


class TestDeletesFollowICloud(_Dirs):
    """The first pass over an adopted tree, with ``remove_obsolete`` on."""

    def _member(self, **photos):
        entry = {
            "id": "member",
            "photos": {
                "library_destinations": {"PrimarySync": "Member"},
                "folder_format": "%Y/%m/%d",
                "all_folder": "",
                "adopt": "icloudpd",
                "folder_timezone": "America/Los_Angeles",
                "remove_obsolete": True,
                **photos,
            },
        }
        return accounts.member_config(_config(self.root, entry), accounts.Account("member", MEMBER))

    def _tree(self):
        self.base = os.path.join(self.root, "photos", "Member")
        self.day = os.path.join(self.base, "2024", "05", "02")
        _write(os.path.join(self.base, ".mounted"), 0)
        for name, size in (("IMG_1.HEIC", 100), ("IMG_1_HEVC.MOV", 200), ("IMG_2-100.HEIC", 100), ("IMG_3.HEIC", 100)):
            _write(os.path.join(self.day, name), size)
        _write(os.path.join(self.day, "deleted-in-icloud.JPG"), 5)

    def _photos(self):
        photos = MagicMock()
        photos.libraries = {
            "PrimarySync": _Library(
                [
                    _photo("IMG_1.HEIC", 100, created=EVENING, video_size=200, record="a"),
                    _photo("IMG_2.HEIC", 100, created=EVENING, record="b"),
                    _photo("IMG_3.HEIC", 100, created=EVENING, record="c"),
                ],
            ),
        }
        return photos

    def _first_pass(self, member):
        report = _in_zone(None, member_report.build, self._photos(), member)
        token = photo_adopt.ADOPTER.set(photo_adopt.Adopter("icloudpd"))
        try:
            contextvars.copy_context().run(sync_photos.sync_photos, member, self._photos())
        finally:
            photo_adopt.ADOPTER.reset(token)
        return report

    def test_only_what_left_icloud_is_deleted(self):
        self._tree()
        report = self._first_pass(self._member())
        self.assertEqual((report["on_disk"], report["old_name"], report["download"]), (2, 2, 0))
        self.assertEqual(report["unclaimed"], 1)
        self.assertTrue(report["deletes"])
        self.assertFalse(report["over_limit"])
        # What the report promised is what happened.
        self.assertEqual(
            sorted(os.listdir(self.day)),
            ["IMG_1.HEIC", "IMG_1_HEVC.MOV", "IMG_2-100.HEIC", "IMG_3.HEIC"],
        )
        self.assertTrue(os.path.exists(os.path.join(self.base, ".mounted")))
        # Filed in local days: no UTC-day folder was made beside the old one.
        self.assertEqual(os.listdir(os.path.join(self.base, "2024", "05")), ["02"])

    def test_over_the_limit_deletes_nothing(self):
        self._tree()
        report = self._first_pass(self._member(obsolete_delete_limit_percent=10))
        self.assertTrue(report["over_limit"])
        self.assertEqual(report["limit"], 10)
        self.assertIn("deleted-in-icloud.JPG", os.listdir(self.day))


class TestSharedLibraryFolder(unittest.TestCase):
    def test_where_the_main_account_keeps_it(self):
        def photos(mapping=None, libraries=None):
            section = {"destination": "/photos/"}
            if mapping is not None:
                section["library_destinations"] = mapping
            if libraries is not None:
                section["filters"] = {"libraries": libraries}
            return {"photos": section}

        for config, expected in (
            (None, None),
            ({}, None),
            ({"photos": "junk"}, None),
            (photos(), "photos"),
            (photos({"PrimarySync": "Me", "SharedLibrary": "Shared"}), "photos/Shared"),
            (photos({"SharedSync-ABC": "Shared/SharedSync-ABC"}), "photos/Shared"),
            (photos({"SharedSync-ABC": "SharedSync-ABC"}), "photos"),
            (photos({"PrimarySync": "Me"}, ["PrimarySync"]), None),
            (photos({"SharedLibrary": "Family"}, ["PrimarySync", "SharedLibrary"]), "photos/Family"),
        ):
            self.assertEqual(accounts.shared_library_folder(config), expected, config)


class TestHouseholdPage(_Dirs):
    def _page(self, config, **member):
        with web_signals.as_account("member"):
            web_signals.record_member(**member)
        with patch.object(web, "_load_current_config", return_value=config):
            client = web.create_app(testing=True).test_client()
            return client.get("/household/member").get_data(as_text=True)

    def _signed_in(self):
        _write(os.path.join(accounts.cookie_directory("member"), "membersession"), 1)

    def test_says_where_the_shared_library_is(self):
        config = _config(self.root, {"id": "member", "username": MEMBER})
        config["photos"]["library_destinations"] = {"PrimarySync": "Main", "SharedLibrary": "Shared"}
        page = self._page(config)
        self.assertIn("Shared Library is in the main backup", page)
        self.assertIn("photos/Shared", page)
        config["photos"]["filters"]["libraries"] = ["PrimarySync"]
        self.assertIn("Shared Library isn't backed up", self._page(config))

    def test_says_when_the_member_owns_a_shared_library(self):
        config = _config(self.root, {"id": "member", "username": MEMBER})
        page = self._page(config, shared_library="Shared/SharedSync-B")
        self.assertIn("Their Shared Library too.", page)
        self.assertIn("Shared/SharedSync-B", page)

    def test_report_says_what_will_be_deleted(self):
        self._signed_in()
        config = _config(self.root, {"id": "member", "username": MEMBER})
        report = {
            "assets": 3,
            "on_disk": 1,
            "old_name": 1,
            "download": 1,
            "download_by_year": {"2026": 1},
            "unclaimed": 4,
            "folder": "Member",
            "samples": {},
            "deletes": True,
            "over_limit": False,
            "limit": 25,
        }
        page = self._page(config, status="review", report=report)
        self.assertIn("Ready to start", page)
        self.assertIn(
            "4 files here aren't in iCloud. Start backup deletes them, and later deletes in iCloud follow.",
            page,
        )
        page = self._page(config, report={**report, "over_limit": True})
        self.assertIn("Too many to delete (over 25%), so they're kept.", page)
        self.assertNotIn("Start backup deletes them", page)
        page = self._page(config, report={**report, "deletes": False})
        self.assertIn("4 files here aren't in iCloud. They're kept.", page)
