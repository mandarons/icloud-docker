"""Tests for a household member's settings, folder safety and own state file."""

import os

import tests  # noqa: F401 - sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import accounts, web_signals
from tests.test_photo_adopt import MAIN, MEMBER, _config, _Dirs


class TestMemberConfig(_Dirs):
    def test_defaults(self):
        config = _config(self.root)
        member = accounts.member_config(config, accounts.Account("member", MEMBER))
        # Drive is on, inside the main account's folder here ("drive" has no
        # parent to share), which drive_conflict then refuses.
        self.assertEqual(member["drive"]["destination"], "drive/member")
        self.assertNotIn("accounts", member)
        self.assertEqual(
            member["app"]["credentials"],
            {"username": MEMBER, "retry_login_interval": 600},
        )
        photos = member["photos"]
        self.assertEqual(photos["library_destinations"], {"PrimarySync": "member"})
        self.assertEqual(photos["filters"]["libraries"], ["PrimarySync"])
        self.assertNotIn("albums", photos["filters"])
        self.assertFalse(photos["remove_obsolete"])
        self.assertFalse(photos["all_albums"])
        self.assertEqual(photos["filename_format"], "simple")
        # The shared config is untouched.
        self.assertEqual(config["app"]["credentials"]["username"], MAIN)
        self.assertEqual(config["photos"]["filters"]["albums"], ["Trip"])

    def test_overrides_and_ignored_keys(self):
        entry = {
            "id": "member",
            "photos": {
                "library_destinations": {"PrimarySync": "Member"},
                "folder_format": "%Y/%m/%d",
                "all_folder": "",
                "adopt": "icloudpd",
                "filename_format": "metadata",
            },
        }
        with self.assertLogs(accounts.LOGGER, level="WARNING") as logs:
            member = accounts.member_config(_config(self.root, entry), accounts.Account("member", MEMBER))
        photos = member["photos"]
        self.assertEqual(photos["library_destinations"], {"PrimarySync": "Member"})
        self.assertEqual(photos["folder_format"], "%Y/%m/%d")
        self.assertEqual(photos["all_folder"], "")
        self.assertEqual(photos["adopt"], "icloudpd")
        self.assertEqual(photos["filename_format"], "simple")
        self.assertIn("filename_format", logs.output[0])

    def test_sparse_config(self):
        config = {
            "app": {"credentials": "junk"},
            "photos": None,
            "accounts": [{"id": "member", "photos": "junk"}],
        }
        member = accounts.member_config(config, accounts.Account("member", MEMBER))
        self.assertEqual(member["app"]["credentials"], {"username": MEMBER})
        self.assertEqual(member["photos"]["filters"], {"libraries": ["PrimarySync"]})
        self.assertEqual(accounts._entry(None, "member"), {})  # noqa: SLF001


class TestFolderSafety(_Dirs):
    def _member(self, config, folder="member"):
        member = accounts.member_config(config, accounts.Account("member", MEMBER))
        member["photos"]["library_destinations"] = {"PrimarySync": folder}
        return member

    def test_separate_folder_is_fine(self):
        config = _config(self.root)
        self.assertIsNone(accounts.folder_conflict(config, self._member(config)))
        self.assertEqual(
            accounts.member_folder(self._member(config)),
            os.path.join(self.root, "photos", "member"),
        )

    def test_inside_a_main_library_folder(self):
        config = _config(self.root)
        self.assertIn(
            "Main",
            accounts.folder_conflict(config, self._member(config, "Main/member")),
        )
        self.assertIn("Shared", accounts.folder_conflict(config, self._member(config, "Shared")))

    def test_whole_destination(self):
        config = _config(self.root)
        self.assertIn(
            "whole photos destination",
            accounts.folder_conflict(config, self._member(config, "")),
        )

    def test_main_without_library_folders_cleans_everything(self):
        config = _config(self.root, photos={"destination": "photos"})
        self.assertEqual(accounts.cleanup_roots(config), [os.path.join(self.root, "photos")])
        self.assertIn("overlaps", accounts.folder_conflict(config, self._member(config)))
        config["photos"] = None
        self.assertEqual(accounts.cleanup_roots(config), [os.path.join(self.root, "photos")])

    def test_other_members(self):
        config = _config(self.root)
        other = os.path.join(self.root, "photos", "member", "kid")
        self.assertIn(
            "another member",
            accounts.folder_conflict(config, self._member(config), [other]),
        )


class TestMemberState(_Dirs):
    def test_member_file_is_separate(self):
        web_signals.record_sync_completion("photos", files_downloaded=5)
        with web_signals.as_account("member"):
            self.assertEqual(web_signals.get_sync_state("photos"), {})
            web_signals.record_member(status="ok", detail="fine")
            web_signals.record_member(detail=None, report={"a": 1})
            self.assertEqual(web_signals.get_member(), {"status": "ok", "report": {"a": 1}})
            self.assertTrue(os.path.isfile(os.path.join(self.dir, "accounts", "member", "state.json")))
        self.assertEqual(web_signals.get_member(), {})
        self.assertEqual(web_signals.get_sync_state("photos")["files_downloaded"], 5)
        self.assertIsNone(web_signals.ACCOUNT.get())

    def test_junk_member_entry(self):
        with web_signals.as_account("member"):
            web_signals._save_state({"_member": "junk"})  # noqa: SLF001
            self.assertEqual(web_signals.get_member(), {})
            web_signals.record_member(status="ok")
            self.assertEqual(web_signals.get_member(), {"status": "ok"})
