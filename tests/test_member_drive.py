"""Tests for a household member's iCloud Drive.

Covers Drive in the member's config and its folder safety, the switch in
config.yaml, the member Drive pass, and the switch on the household page.
"""

import os
from unittest.mock import MagicMock, patch

import tests  # noqa: F401 - sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import accounts, member_sync, settings_view, web, web_signals
from tests.test_photo_adopt import MAIN, MEMBER, _config, _Dirs, _write
from tests.test_web import _csrf_post


def _with_drive(root, entry=None, destination="drive/Main"):
    config = _config(root, entry or {"id": "member", "username": MEMBER})
    config["drive"] = {
        "destination": destination,
        "sync_interval": 600,
        "filters": {"folders": ["Work"]},
        "ignore": ["drive/Main/Secret/*"],
        "remove_obsolete": True,
    }
    return config


ME = accounts.Account("member", MEMBER)


class TestMemberDrive(_Dirs):
    def test_beside_the_main_accounts_folder(self):
        member = accounts.member_config(_with_drive(self.root), ME)
        self.assertEqual(member["drive"]["destination"], "drive/member")
        self.assertNotIn("filters", member["drive"])
        self.assertNotIn("ignore", member["drive"])
        self.assertFalse(member["drive"]["remove_obsolete"])
        self.assertEqual(member["drive"]["sync_interval"], 600)
        self.assertEqual(accounts.drive_folder(member), os.path.join(self.root, "drive", "member"))

    def test_entry_settings(self):
        entry = {
            "id": "member",
            "drive": {
                "enabled": True,
                "destination": "drive/M",
                "remove_obsolete": True,
                "filters": {"x": 1},
            },
        }
        with self.assertLogs(accounts.LOGGER, "WARNING") as logs:
            member = accounts.member_config(_with_drive(self.root, entry), ME)
        self.assertEqual(
            (member["drive"]["destination"], member["drive"]["remove_obsolete"]),
            ("drive/M", True),
        )
        self.assertNotIn("enabled", member["drive"])
        self.assertIn("drive.filters", "\n".join(logs.output))

    def test_on_and_off(self):
        for value, on in (
            (None, True),
            (True, True),
            ({}, True),
            (False, False),
            ({"enabled": False}, False),
        ):
            entry = {"id": "member"} if value is None else {"id": "member", "drive": value}
            config = _with_drive(self.root, entry)
            self.assertEqual(accounts.drive_enabled(config, ME), on, value)
            self.assertEqual("drive" in accounts.member_config(config, ME), on, value)
        no_drive = _config(self.root)
        no_drive.pop("drive")
        self.assertFalse(accounts.drive_enabled(no_drive, ME))
        self.assertIsNone(accounts.drive_folder(no_drive))
        self.assertIsNone(accounts.drive_conflict(no_drive, accounts.member_config(no_drive, ME)))

    def test_folder_safety(self):
        config = _with_drive(self.root)
        member = accounts.member_config(config, ME)
        self.assertIsNone(accounts.drive_conflict(config, member))
        other = os.path.join(self.root, "drive", "member")
        self.assertIn("another member", accounts.drive_conflict(config, member, [other]))
        # The main account's Drive at the volume root: no folder beside it.
        rooted = _with_drive(self.root, destination="drive")
        self.assertIn(
            "inside the main account's",
            accounts.drive_conflict(rooted, accounts.member_config(rooted, ME)),
        )


class TestDriveSwitchInConfig(_Dirs):
    def _file(self, accounts_yaml):
        path = os.path.join(self.dir, "config.yaml")
        with open(path, "w") as f:
            f.write(f"app:\n  root: {self.root}\n  credentials:\n    username: {MAIN}\naccounts:\n{accounts_yaml}")
        return path

    def _read(self, path):
        from src import read_config

        return read_config(config_path=path)["accounts"]

    def test_switch(self):
        path = self._file("  - id: member\n  - id: kid\n    drive:\n      destination: drive/K\n")
        settings_view.set_member_drive(path, "member", False)
        settings_view.set_member_drive(path, "kid", False)
        entries = {e["id"]: e for e in self._read(path)}
        self.assertEqual(entries["member"]["drive"], {"enabled": False})
        self.assertEqual(entries["kid"]["drive"], {"destination": "drive/K", "enabled": False})
        with self.assertRaises(settings_view.SettingError):
            settings_view.set_member_drive(path, "nobody", True)


class TestMemberDrivePass(_Dirs):
    def setUp(self):
        super().setUp()
        self.config = _with_drive(self.root)
        self.member = accounts.member_config(self.config, ME)
        self.main_marker = os.path.join(self.root, "drive", "Main", ".mounted")

    def test_mount_check_before_anything_is_created(self):
        with patch.object(
            member_sync.config_parser,
            "get_drive_require_mount_marker",
            return_value=True,
        ):
            self.assertFalse(member_sync._drive_mounted(self.config, self.member))  # noqa: SLF001
            note = member_sync._drive_pass(MagicMock(), self.config, self.member)  # noqa: SLF001
            self.assertIn("isn't mounted", note)
            self.assertFalse(os.path.exists(os.path.join(self.root, "drive", "member")))
            _write(self.main_marker, 0)
            self.assertTrue(member_sync._drive_mounted(self.config, self.member))  # noqa: SLF001
        with patch.object(
            member_sync.config_parser,
            "get_drive_require_mount_marker",
            return_value=False,
        ):
            self.assertTrue(member_sync._drive_mounted(self.config, {}))  # noqa: SLF001

    def _run(self, effect=None):
        _write(self.main_marker, 0)
        folder = os.path.join(self.root, "drive", "member")

        def fake(config, drive):
            _write(os.path.join(folder, "new.txt"), 3)
            if effect:
                raise effect

        with (
            web_signals.as_account("member"),
            patch("src.sync_drive.sync_drive", side_effect=fake),
        ):
            _write(os.path.join(folder, "old.txt"), 1)
            note = member_sync._drive_pass(MagicMock(), self.config, self.member)  # noqa: SLF001
            return note, web_signals.get_sync_state("drive")

    def test_counts(self):
        note, state = self._run()
        self.assertIsNone(note)
        self.assertEqual((state["files_downloaded"], state["files_skipped"]), (1, 1))
        self.assertFalse(state.get("running_since"))
        self.assertIsNone(state.get("files_removed"))
        self.member["drive"]["remove_obsolete"] = True
        self.assertEqual(self._run()[1]["files_removed"], 0)

    def test_failure_is_a_sentence_not_a_crash(self):
        with self.assertLogs(member_sync.LOGGER, "ERROR"):
            note, state = self._run(RuntimeError("gone"))
        self.assertEqual(note, "Drive's last pass failed: gone")
        self.assertFalse(state.get("running_since"))

    def test_a_drive_problem_leaves_photos_running(self):
        config = _with_drive(self.root, destination="drive")
        _write(os.path.join(accounts.cookie_directory("member"), "s"), 1)
        _write(os.path.join(self.root, "photos", ".mounted"), 0)
        api = MagicMock()
        api.requires_2fa = False
        with (
            patch.object(member_sync, "_resume", return_value=api),
            patch.object(member_sync, "_pass") as real_pass,
            self.assertLogs(member_sync.LOGGER, "WARNING"),
        ):
            member_sync.run_member(config, ME, [])
        member, problem = real_pass.call_args.args[2], real_pass.call_args.args[4]
        self.assertNotIn("drive", member)
        self.assertIn("inside the main account's", problem)

    def test_the_pass_runs_drive_after_photos(self):
        api = MagicMock()
        with (
            web_signals.as_account("member"),
            patch("src.sync_photos.sync_photos", return_value=(1, 0)),
            patch.object(member_sync, "_drive_pass", return_value="Drive is paused.") as drive,
        ):
            member_sync._pass(api, self.config, self.member, None)  # noqa: SLF001
            self.assertEqual(web_signals.get_member()["detail"], "Drive is paused.")
            drive.assert_called_once()
            self.member.pop("drive")
            member_sync._pass(api, self.config, self.member, None, "Drive is off: x.")  # noqa: SLF001
            self.assertEqual(web_signals.get_member()["detail"], "Drive is off: x.")


class _Web(_Dirs):
    def setUp(self):
        super().setUp()
        self.config = _with_drive(self.root, {"id": "member", "username": MEMBER, "email": "her@example.com"})
        patcher = patch.object(web, "_load_current_config", side_effect=lambda: self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = web.create_app(testing=True).test_client()
        _write(os.path.join(accounts.cookie_directory("member"), "s"), 1)


class TestHouseholdDriveSwitch(_Web):
    def test_household_drive_switch(self):
        with (
            patch.object(settings_view, "set_member_drive") as switch,
            patch.object(member_sync, "wake"),
        ):
            response = _csrf_post(self.client, "/household/member/drive", {"enabled": "1"})
            self.assertEqual(_csrf_post(self.client, "/household/nobody/drive").status_code, 302)
        switch.assert_called_once_with(web._current_config_path(), "member", True)  # noqa: SLF001
        self.assertTrue(response.headers["Location"].endswith("/household/member"))
        self.assertEqual(self.client.post("/household/member/drive").status_code, 403)
        page = self.client.get("/household/member").get_data(as_text=True)
        self.assertIn("iCloud Drive", page)
        self.assertIn("Turn off", page)
