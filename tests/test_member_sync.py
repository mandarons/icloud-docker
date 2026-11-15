"""Tests for household members' photo backup.

Covers the member config (``accounts.member_config``), the folder safety
check, per-member state (``web_signals.as_account``), the read-only
report (``member_report``), the member thread (``member_sync``), its
notifications and its dashboard controls.
"""

import datetime
import logging
import os
import threading
import unittest
from unittest.mock import MagicMock, patch

from icloudpy import exceptions

import tests  # noqa: F401 - sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import accounts, config_parser, member_report, member_sync, photo_adopt, sync_photos, web_signals
from tests.test_photo_adopt import MEMBER, UTC, _config, _Dirs, _photo, _write


class _FakeLibrary:
    def __init__(self, photos, fail=None):
        self._photos = photos
        self._fail = fail

    @property
    def all(self):
        yield from self._photos
        if self._fail:
            raise self._fail


def _fake_api(photos, fail=None):
    api = MagicMock()
    api.requires_2fa = False
    api.photos.libraries = {"PrimarySync": _FakeLibrary(photos, fail)}
    return api


class TestReport(_Dirs):
    def _member(self):
        entry = {
            "id": "member",
            "photos": {
                "library_destinations": {"PrimarySync": "Member"},
                "folder_format": "%Y/%m/%d",
                "all_folder": "",
                "adopt": "icloudpd",
            },
        }
        config = _config(self.root, entry)
        return accounts.member_config(config, accounts.Account("member", MEMBER))

    def test_classifies_every_file(self):
        base = os.path.join(self.root, "photos", "Member")
        day = os.path.join(base, "2024", "05", "03")
        _write(os.path.join(day, "IMG_1.HEIC"), 100)
        _write(os.path.join(day, "IMG_1_HEVC.MOV"), 200)
        _write(os.path.join(day, "IMG_2-100.HEIC"), 100)
        _write(os.path.join(day, "deleted-in-icloud.JPG"), 5)
        _write(os.path.join(base, ".mounted"), 0)
        _write(os.path.join(base, "@eaDir", "thumb.jpg"), 5)
        photos = [
            _photo("IMG_1.HEIC", 100, video_size=200),
            _photo("IMG_2.HEIC", 100),
            _photo("IMG_3.HEIC", 100, created=datetime.datetime(2026, 1, 2, tzinfo=UTC)),
            _photo("IMG_4.HEIC", 100),
        ]
        photos[3].created = None
        photos[2].versions["full"] = {"type": "public.jpeg", "size": 1}
        report = member_report.build(_fake_api(photos).photos, self._member())
        self.assertEqual(report["assets"], 4)
        self.assertEqual(report["on_disk"], 1)
        self.assertEqual(report["old_name"], 2)
        self.assertEqual(report["download"], 1)
        self.assertEqual(report["download_by_year"], {"2026": 1})
        self.assertEqual(report["unreadable"], 1)
        # Counted the way cleanup counts: everything but the mount marker,
        # Synology's thumbnails included.
        self.assertEqual(report["unclaimed"], 2)
        self.assertEqual(
            sorted(report["samples"]["unclaimed"]),
            [os.path.join("2024", "05", "03", "deleted-in-icloud.JPG"), os.path.join("@eaDir", "thumb.jpg")],
        )
        self.assertFalse(report["deletes"])
        self.assertFalse(report["over_limit"])
        self.assertEqual(report["folder"], "Member")
        self.assertNotIn("stopped", report)
        # Read-only: nothing was created for the photos that would download.
        self.assertFalse(os.path.exists(os.path.join(base, "2026")))

    def test_partial_walk_and_missing_folder(self):
        report = member_report.build(
            _fake_api([_photo("IMG_1.HEIC", 100)], fail=ValueError("boom")).photos,
            self._member(),
        )
        self.assertEqual(report["stopped"], "boom")
        self.assertEqual(report["unclaimed"], 0)

    def test_library_base_with_all_folder(self):
        member = accounts.member_config(_config(self.root), accounts.Account("member", MEMBER))
        self.assertEqual(
            member_report.library_base(member),
            os.path.join(self.root, "photos", "member", "all"),
        )


class TestMemberThread(_Dirs):
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.root, "photos"))
        _write(os.path.join(self.root, "photos", ".mounted"), 0)
        self.entry = {"id": "member", "username": MEMBER}
        self.config = _config(self.root, self.entry)
        self.config["photos"]["require_mount_marker"] = True
        announce = patch.object(member_sync, "_announce")
        announce.start()
        self.addCleanup(announce.stop)

    def _sign_in(self):
        _write(os.path.join(accounts.cookie_directory("member"), "membersession"), 1)

    def _member_state(self):
        with web_signals.as_account("member"):
            return web_signals.get_member()

    def _run(self, api=None, side_effect=None):
        with patch("src.sync.get_api_instance", return_value=api, side_effect=side_effect) as get_api:
            member_sync.run_once(self.config)
        return get_api

    def test_waits_for_first_sign_in(self):
        get_api = self._run()
        get_api.assert_not_called()
        self.assertEqual(self._member_state()["status"], "needs_sign_in")

    def test_blocked_folder(self):
        self.entry["photos"] = {"library_destinations": {"PrimarySync": "Main/member"}}
        self._sign_in()
        with self.assertLogs(member_sync.LOGGER, level="ERROR"):
            self._run()
        self.assertEqual(self._member_state()["status"], "blocked")

    def test_no_photos_section(self):
        self._sign_in()
        del self.config["photos"]
        self._run()
        self.assertEqual(self._member_state()["status"], "blocked")

    def test_session_rejected_is_never_retried_with_a_password(self):
        self._sign_in()
        get_api = self._run(side_effect=exceptions.ICloudPyNoStoredPasswordAvailableException("no"))
        self.assertIsNone(get_api.call_args.kwargs["password"])
        self.assertEqual(
            get_api.call_args.kwargs["cookie_directory"],
            accounts.cookie_directory("member"),
        )
        self.assertEqual(self._member_state()["status"], "needs_sign_in")

    def test_outage(self):
        self._sign_in()
        self._run(side_effect=ConnectionError("down"))
        self.assertEqual(self._member_state()["status"], "error")

    def test_code_wanted_again(self):
        self._sign_in()
        api = _fake_api([])
        api.requires_2fa = True
        self._run(api)
        self.assertIn("6-digit", self._member_state()["detail"])

    def test_missing_mount_marker(self):
        self._sign_in()
        os.unlink(os.path.join(self.root, "photos", ".mounted"))
        self._run(_fake_api([]))
        self.assertEqual(self._member_state()["status"], "blocked")

    def test_adopting_member_gets_a_report_first(self):
        self.entry["photos"] = {
            "library_destinations": {"PrimarySync": "Member"},
            "adopt": "icloudpd",
        }
        self._sign_in()
        with patch.object(sync_photos, "sync_photos") as real_pass:
            self._run(_fake_api([_photo("IMG_1.HEIC", 100)]))
            state = self._member_state()
            self.assertEqual(state["status"], "review")
            self.assertEqual(state["report"]["download"], 1)
            # The report stands until someone acts on it.
            with patch.object(member_sync, "_report") as again:
                self._run(_fake_api([]))
            again.assert_not_called()
            real_pass.assert_not_called()

    def test_approved_member_backs_up_with_the_adopter(self):
        self.entry["photos"] = {
            "library_destinations": {"PrimarySync": "Member"},
            "adopt": "icloudpd",
        }
        self._sign_in()
        with web_signals.as_account("member"):
            web_signals.record_member(approved=True)
        seen = {}

        def fake_pass(config, photos):
            seen["adopter"] = photo_adopt.ADOPTER.get()
            seen["account"] = web_signals.ACCOUNT.get()
            seen["config"] = config
            seen["adopter"].adopted = 7
            return 3, 1

        with patch.object(sync_photos, "sync_photos", side_effect=fake_pass):
            self._run(_fake_api([]))
        self.assertIsInstance(seen["adopter"], photo_adopt.Adopter)
        self.assertEqual(seen["account"], "member")
        self.assertEqual(seen["config"]["app"]["credentials"]["username"], MEMBER)
        self.assertIsNone(photo_adopt.ADOPTER.get())
        state = self._member_state()
        self.assertEqual((state["status"], state["adopted"]), ("ok", 7))
        with web_signals.as_account("member"):
            photos = web_signals.get_sync_state("photos")
        self.assertEqual((photos["files_downloaded"], photos["errors"]), (3, 1))
        self.assertNotIn("running_since", photos)
        # The primary's card never saw any of it.
        self.assertEqual(web_signals.get_sync_state("photos"), {})

    def test_plain_member_and_odd_result(self):
        self._sign_in()
        with patch.object(sync_photos, "sync_photos", return_value=None) as real_pass:
            self._run(_fake_api([]))
        real_pass.assert_called_once()
        state = self._member_state()
        self.assertEqual(state["status"], "ok")
        self.assertNotIn("adopted", state)

    def test_one_member_failing_does_not_stop_the_next(self):
        self.config["accounts"] = [
            {"id": "member", "username": MEMBER},
            {"id": "kid", "username": "kid@example.com"},
        ]
        calls = []

        def boom(config, account, others, other_drives=(), owners=None):
            calls.append(account.id)
            if account.id == "member":
                msg = "bad"
                raise RuntimeError(msg)

        with patch.object(member_sync, "run_member", side_effect=boom), self.assertLogs(member_sync.LOGGER, "ERROR"):
            member_sync.run_once(self.config)
        self.assertEqual(calls, ["member", "kid"])
        self.assertEqual(self._member_state()["status"], "error")
        member_sync.run_once(None)

    def test_interval(self):
        self.assertEqual(member_sync._interval(None), 3600)  # noqa: SLF001
        self.assertEqual(member_sync._interval({"photos": {"sync_interval": 60}}), 300)  # noqa: SLF001
        self.assertEqual(member_sync._interval({"photos": {"sync_interval": 7200}}), 7200)  # noqa: SLF001
        self.assertEqual(member_sync._interval({"photos": {"sync_interval": -1}}), 3600)  # noqa: SLF001
        with patch.object(config_parser, "get_photos_sync_interval", side_effect=ValueError):
            self.assertEqual(member_sync._interval({"photos": {}}), 3600)  # noqa: SLF001

    def test_load_config(self):
        with patch.dict(os.environ, {"ENV_CONFIG_FILE_PATH": os.path.join(self.dir, "missing.yaml")}):
            self.assertIsNone(member_sync._load_config())  # noqa: SLF001
        path = _write(os.path.join(self.dir, "config.yaml"), 1)
        with (
            patch.dict(os.environ, {"ENV_CONFIG_FILE_PATH": path}),
            patch.object(member_sync, "read_config", side_effect=KeyError("x")),
            self.assertLogs(member_sync.LOGGER, "WARNING"),
        ):
            self.assertIsNone(member_sync._load_config())  # noqa: SLF001
        with (
            patch.dict(os.environ, {"ENV_CONFIG_FILE_PATH": path}),
            patch.object(member_sync, "read_config", return_value={"a": 1}),
        ):
            self.assertEqual(member_sync._load_config(), {"a": 1})  # noqa: SLF001

    def test_wake_and_thread(self):
        member_sync._WAKE.clear()  # noqa: SLF001
        member_sync.wake()
        self.assertTrue(member_sync._WAKE.is_set())  # noqa: SLF001
        member_sync._WAKE.clear()  # noqa: SLF001
        started = threading.Event()
        with patch.object(member_sync, "_loop", side_effect=started.set), patch.object(member_sync, "_THREAD", None):
            thread = member_sync.start_in_thread()
            self.assertTrue(started.wait(5))
            thread.join(5)
            alive = MagicMock()
            alive.is_alive.return_value = True
            member_sync._THREAD = alive  # noqa: SLF001
            self.assertIs(member_sync.start_in_thread(), alive)

    def test_log_prefix(self):
        handler = logging.StreamHandler()
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            member_sync._install_log_prefix()  # noqa: SLF001
            member_sync._install_log_prefix()  # noqa: SLF001
            prefixes = [f for f in handler.filters if isinstance(f, member_sync._AccountPrefix)]  # noqa: SLF001
            self.assertEqual(len(prefixes), 1)
        finally:
            root.removeHandler(handler)
        prefix = member_sync._AccountPrefix()  # noqa: SLF001
        record = logging.LogRecord("x", logging.INFO, "f", 1, "hello", None, None)
        prefix.filter(record)
        self.assertEqual(record.msg, "hello")
        with web_signals.as_account("member"):
            prefix.filter(record)
            prefix.filter(record)
        self.assertEqual(record.msg, "[member] hello")

    def test_sign_in_wakes_the_thread(self):
        from flask import Flask

        from src import member_signin

        member_sync._WAKE.clear()  # noqa: SLF001
        app = Flask(__name__)
        app.secret_key = b"test"
        os.makedirs(member_signin._staging("member"))  # noqa: SLF001 - a sign-in in progress
        with app.test_request_context():
            member_signin._finish(accounts.Account("member", MEMBER), MEMBER)  # noqa: SLF001
        self.assertTrue(member_sync._WAKE.is_set())  # noqa: SLF001
        member_sync._WAKE.clear()  # noqa: SLF001


ZONE = "SharedSync-11111111-2222-3333-4444-555555555555"
OTHER_ZONE = "SharedSync-AAAAAAAA-2222-3333-4444-555555555555"


class TestSharedZoneFolder(unittest.TestCase):
    """Where a Shared Library a member owns lands."""

    def _folder(self, mapping):
        config = {"photos": {"destination": "photos", "library_destinations": mapping}}
        return accounts.shared_zone_folder(config, ZONE, "member")

    def test_beside_the_main_accounts_library_when_named_for_its_zone(self):
        self.assertEqual(self._folder({"SharedLibrary": f"Shared/{OTHER_ZONE}"}), f"Shared/{ZONE}")
        self.assertEqual(self._folder({OTHER_ZONE: OTHER_ZONE}), ZONE)

    def test_a_sibling_when_the_main_accounts_folder_is_the_library(self):
        self.assertEqual(self._folder({"SharedLibrary": "Shared/"}), "Shared-member")
        self.assertEqual(self._folder({"SharedLibrary": ""}), "Shared-member")

    def test_shared_when_the_main_account_has_none(self):
        self.assertEqual(self._folder({"PrimarySync": "Main"}), f"Shared/{ZONE}")
        self.assertEqual(accounts.shared_zone_folder({}, ZONE, "member"), f"Shared/{ZONE}")


class TestMembersSharedLibrary(_Dirs):
    """Every Shared Library is backed up once, by exactly one account."""

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.root, "photos"))
        self.config = _config(self.root, {"id": "member", "username": MEMBER})
        self.config["photos"]["library_destinations"] = {"PrimarySync": "Main"}
        announce = patch.object(member_sync, "_announce")
        announce.start()
        self.addCleanup(announce.stop)

    def _sign_in(self, account_id="member"):
        _write(os.path.join(accounts.cookie_directory(account_id), "session"), 1)

    def _api(self, *zones):
        api = _fake_api([])
        for zone in zones:
            api.photos.libraries[zone] = _FakeLibrary([])
        return api

    def _passes(self, apis):
        """Run one cycle; return each member's photos config as its pass saw it."""
        seen = {}

        def fake_pass(config, photos):
            seen[web_signals.ACCOUNT.get()] = config["photos"]
            return 0, 0

        with (
            patch("src.sync.get_api_instance", side_effect=lambda **kw: apis[kw["cookie_directory"]]),
            patch.object(sync_photos, "sync_photos", side_effect=fake_pass),
        ):
            member_sync.run_once(self.config)
        return seen

    def _state(self, account_id="member"):
        with web_signals.as_account(account_id):
            return web_signals.get_member()

    def test_the_owner_backs_it_up_beside_the_main_accounts(self):
        self.config["photos"]["library_destinations"] = {"PrimarySync": "Main", "SharedLibrary": f"Shared/{OTHER_ZONE}"}
        self._sign_in()
        seen = self._passes({accounts.cookie_directory("member"): self._api(ZONE)})
        photos = seen["member"]
        self.assertEqual(photos["filters"]["libraries"], ["PrimarySync", ZONE])
        self.assertEqual(photos["library_destinations"], {"PrimarySync": "member", ZONE: f"Shared/{ZONE}"})
        self.assertFalse(photos["remove_obsolete"])
        self.assertEqual(self._state()["shared_library"], f"Shared/{ZONE}")

    def test_never_twice_when_the_main_account_already_backs_it_up(self):
        web_signals.record_library_finished(ZONE, ok=True)
        self._sign_in()
        with self.assertLogs(member_sync.LOGGER, level="INFO") as logs:
            seen = self._passes({accounts.cookie_directory("member"): self._api(ZONE)})
        self.assertEqual(seen["member"]["filters"]["libraries"], ["PrimarySync"])
        self.assertNotIn(ZONE, seen["member"]["library_destinations"])
        self.assertIn("already backed up by the main account", "\n".join(logs.output))
        self.assertNotIn("shared_library", self._state())

    def test_never_twice_between_members(self):
        self.config["accounts"] = [
            {"id": "member", "username": MEMBER},
            {"id": "second", "username": "second@example.com"},
        ]
        self._sign_in()
        self._sign_in("second")
        apis = {
            accounts.cookie_directory("member"): self._api(ZONE),
            accounts.cookie_directory("second"): self._api(ZONE),
        }
        seen = self._passes(apis)
        self.assertIn(ZONE, seen["member"]["filters"]["libraries"])
        self.assertEqual(seen["second"]["filters"]["libraries"], ["PrimarySync"])
        # Next cycle it stays with the member who has been backing it up,
        # whatever order the accounts run in.
        with web_signals.as_account("member"):
            web_signals.record_library_finished(ZONE, ok=True)
        self.config["accounts"].reverse()
        seen = self._passes(apis)
        self.assertEqual(seen["second"]["filters"]["libraries"], ["PrimarySync"])
        self.assertIn(ZONE, seen["member"]["filters"]["libraries"])

    def test_two_libraries_two_folders(self):
        self.config["accounts"] = [
            {"id": "member", "username": MEMBER},
            {"id": "second", "username": "second@example.com"},
        ]
        self._sign_in()
        self._sign_in("second")
        seen = self._passes(
            {
                accounts.cookie_directory("member"): self._api(ZONE),
                accounts.cookie_directory("second"): self._api(OTHER_ZONE),
            },
        )
        self.assertEqual(seen["member"]["library_destinations"][ZONE], f"Shared/{ZONE}")
        self.assertEqual(seen["second"]["library_destinations"][OTHER_ZONE], f"Shared/{OTHER_ZONE}")

    def test_not_where_the_main_accounts_cleanup_walks(self):
        # A folder the main account maps for something else: its cleanup
        # walks it, so the member's library can't go inside.
        self.config["photos"]["library_destinations"] = {"PrimarySync": "Main", "Old": "Shared"}
        self._sign_in()
        with self.assertLogs(member_sync.LOGGER, level="WARNING") as logs:
            seen = self._passes({accounts.cookie_directory("member"): self._api(ZONE)})
        self.assertEqual(seen["member"]["filters"]["libraries"], ["PrimarySync"])
        self.assertIn("not backing up member's Shared Library", "\n".join(logs.output))

    def test_a_listing_failure_keeps_the_personal_library(self):
        self._sign_in()
        api = _fake_api([])
        type(api.photos).libraries = property(lambda _self: (_ for _ in ()).throw(ConnectionError("down")))
        with self.assertLogs(member_sync.LOGGER, level="WARNING"):
            seen = self._passes({accounts.cookie_directory("member"): api})
        self.assertEqual(seen["member"]["filters"]["libraries"], ["PrimarySync"])


class TestAnnouncements(_Dirs):
    def _status(self, status, **fields):
        with web_signals.as_account("member"):
            member_sync._status(status, **fields)  # noqa: SLF001

    def test_report_and_lost_sign_in_are_announced_once(self):
        config = {"app": {"web_ui": {"public_url": "https://home.example.com/"}}}
        with patch.object(member_sync, "_load_config", return_value=config), patch("src.notify.send_household") as send:
            self._status("needs_sign_in")  # never signed in: not news
            self._status("checking")
            self._status("review", report={"download": 1234})
            self._status("review", report={"download": 1234})
            self._status("ok")
            self._status("needs_sign_in")
        messages = [c.args[1] for c in send.call_args_list]
        self.assertEqual(len(messages), 2)
        self.assertIn("1,234 photos", messages[0])
        self.assertIn("https://home.example.com/household/member", messages[0])
        self.assertIn("new link", messages[1])

    def test_without_public_url_or_config(self):
        with (
            patch.object(member_sync, "_load_config", return_value={"app": {}}),
            patch("src.notify.send_household") as send,
        ):
            self._status("review")
        self.assertIn("Household card", send.call_args.args[1])
        with patch.object(member_sync, "_load_config", return_value=None), patch("src.notify.send_household") as send:
            self._status("checking")
            self._status("review")
        send.assert_not_called()

    def test_send_failure_is_logged(self):
        with (
            patch.object(member_sync, "_load_config", return_value={"app": {}}),
            patch("src.notify.send_household", side_effect=RuntimeError("down")),
            self.assertLogs(member_sync.LOGGER, "WARNING"),
        ):
            self._status("review")


class TestSendHousehold(unittest.TestCase):
    def test_every_channel_once(self):
        from src import notify

        with (
            patch.object(notify, "_send_telegram_no_throttle", return_value=False) as telegram,
            patch.object(notify, "_send_discord_no_throttle", side_effect=RuntimeError("x")),
            patch.object(notify, "_send_pushover_no_throttle", return_value=True),
            patch.object(notify, "_send_email_no_throttle", return_value=False) as email,
            self.assertLogs(notify.LOGGER, "WARNING"),
        ):
            self.assertTrue(notify.send_household({}, "hello"))
        telegram.assert_called_once_with({}, "hello", dry_run=False)
        self.assertEqual(email.call_args.args[2], "iCloud backup: household")
