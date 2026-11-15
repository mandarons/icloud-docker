"""Tests for what the dashboard says (``src.dashboard_view``).

Each lifecycle stage of the main account and of a household member, the
headline that sums them up, and the log line.
"""

import unittest

from src import dashboard_view as view


def _service(name="Photos", **over):
    service = {
        "name": name,
        "sync_interval_s": 43200,
        "require_mount_marker": True,
        "marker_present": True,
        "libraries": [],
        "stats": {
            "completed_at": 100,
            "last_sync_relative": "9 min ago",
            "files_downloaded": 1,
            "files_skipped": 38714,
            "files_removed": 0,
            "errors": 0,
        },
        "syncing_since_relative": None,
    }
    service.update(over)
    return service


def _status(**over):
    status = {
        "username": "someone@example.com",
        "auth_state": "ready",
        "auth_blocked_reason": None,
        "trust_days_remaining": 84,
        "services": [_service()],
        "household": [],
    }
    status.update(over)
    return status


def _member(status=None, saved=True, **backup):
    return {
        "id": "alex",
        "username": "j@example.com" if saved else None,
        "session_saved": saved,
        "backup": {"status": status, **backup},
    }


class TestWords(unittest.TestCase):
    def test_library_names(self):
        self.assertEqual(view.library_label("PrimarySync"), "Personal library")
        self.assertEqual(view.library_label("SharedSync-ABC"), "Shared Library")
        self.assertEqual(view.library_label("SharedLibrary"), "Shared Library")
        self.assertEqual(view.library_label("Other"), "Other")

    def test_schedule(self):
        for seconds, words in (
            (43200, "every 12 h"),
            (86400, "every day"),
            (172800, "every 2 days"),
            (600, "every 10 min"),
            (45, "every 45 s"),
            (-1, "once, then stops"),
            ("junk", ""),
            (None, ""),
        ):
            self.assertEqual(view.every(seconds), words, seconds)

    def test_avatar_colour_comes_from_the_name(self):
        self.assertEqual(view._hue("alex"), view._hue("Alex"))  # noqa: SLF001
        self.assertTrue(0 <= view._hue("alex") < 360)  # noqa: SLF001


class TestServices(unittest.TestCase):
    def _one(self, **over):
        return view.people(_status(services=[_service(**over)]))[0]["services"][0]

    def test_backed_up(self):
        service = self._one()
        self.assertEqual((service["tone"], service["when"]), ("ok", "Backed up 9 min ago"))
        self.assertEqual(service["facts"], "1 new · 38,714 already here")
        self.assertEqual(service["schedule"], "every 12 h")

    def test_facts_name_removals_and_failures(self):
        stats = {"last_sync_relative": "1 h ago", "files_removed": 3, "errors": 2}
        self.assertEqual(self._one(stats=stats)["facts"], "3 removed · 2 failed")

    def test_running(self):
        service = self._one(syncing_since_relative="2 min ago")
        self.assertEqual(
            (service["tone"], service["when"]),
            ("busy", "Syncing now · started 2 min ago"),
        )

    def test_unmounted(self):
        service = self._one(marker_present=False)
        self.assertEqual(service["tone"], "err")
        self.assertTrue(service["marker_missing"])
        self.assertEqual(self._one(marker_present=False, require_mount_marker=False)["tone"], "ok")

    def test_a_failed_library(self):
        failed = [{"name": "PrimarySync", "state": "failed"}]
        self.assertEqual(self._one(libraries=failed)["tone"], "warn")
        services = [_service(libraries=failed), _service("Drive", marker_present=False)]
        me = view.people(_status(services=services))[0]
        self.assertEqual(me["sentence"], "A Photos library failed; Drive is paused: its folder isn't mounted")
        self.assertEqual(
            self._one(libraries=failed, stats=None)["when"],
            "Last backup not finished",
        )

    def test_never_run(self):
        service = self._one(stats=None)
        self.assertEqual(
            (service["tone"], service["when"], service["facts"]),
            ("idle", "Waiting for the first backup", ""),
        )

    def test_indexing_said_once_when_every_library_is(self):
        both = [
            {"name": "PrimarySync", "indexing": True},
            {"name": "SharedSync-A", "indexing": True},
        ]
        service = self._one(libraries=both)
        self.assertTrue(service["all_indexing"])
        self.assertEqual(
            [lib["label"] for lib in service["libraries"]],
            ["Personal library", "Shared Library"],
        )
        self.assertFalse(self._one(libraries=[both[0], {"name": "SharedSync-A"}])["all_indexing"])
        self.assertFalse(self._one()["all_indexing"])


class TestMainAccount(unittest.TestCase):
    def _me(self, **over):
        return view.people(_status(**over))[0]

    def test_not_set_up(self):
        me = self._me(auth_state=None, username=None)
        self.assertEqual(
            (me["tone"], me["sentence"], me["action"]["label"]),
            ("err", "No Apple ID set up yet", "Set up"),
        )
        self.assertEqual((me["name"], me["initial"]), ("Main account", "?"))

    def test_first_sign_in(self):
        me = self._me(auth_state="setup_needed")
        self.assertEqual((me["tone"], me["action"]["href"]), ("warn", "/auth"))

    def test_stopped_says_why(self):
        for reason, words in (
            ("session_unusable", "no longer valid"),
            ("sign_in_failed", "can be an outage"),
            ("2fa_required", "second factor"),
            (None, "second factor"),
        ):
            me = self._me(auth_state="reauth_needed", auth_blocked_reason=reason)
            self.assertEqual(me["sentence"], "Backups are stopped")
            self.assertIn(words, me["detail"])

    def test_backing_up(self):
        me = self._me(services=[_service(syncing_since_relative="2 min ago"), _service("Drive")])
        self.assertEqual(
            (me["tone"], me["sentence"], me["detail"]),
            ("busy", "Backing up now", "Photos started 2 min ago"),
        )

    def test_trouble_names_the_service(self):
        me = self._me(services=[_service(marker_present=False), _service("Drive")])
        self.assertEqual(
            (me["tone"], me["sentence"]),
            ("err", "Photos is paused: its folder isn't mounted"),
        )

    def test_the_oldest_backup_is_the_one_that_counts(self):
        fresh = _service("Drive", stats={"completed_at": 200, "last_sync_relative": "9 min ago"})
        stale = _service(stats={"completed_at": 100, "last_sync_relative": "12 h ago"})
        self.assertEqual(self._me(services=[fresh, stale])["sentence"], "Backed up 12 h ago")

    def test_nothing_run_yet(self):
        me = self._me(services=[_service(stats=None)])
        self.assertEqual((me["tone"], me["sentence"]), ("idle", "Waiting for the first backup"))
        self.assertEqual(self._me(services=[])["tone"], "idle")

    def test_trust(self):
        me = self._me(trust_days_remaining=0)
        self.assertEqual((me["tone"], me["action"]["post"]), ("warn", "/auth/refresh-trust"))
        self.assertIn("run out", me["detail"])
        me = self._me(trust_days_remaining=1)
        self.assertIn("in 1 day.", me["detail"])
        self.assertIn("in 3 days.", self._me(trust_days_remaining=3)["detail"])
        # A worse problem is not hidden behind a trust reminder.
        broken = self._me(trust_days_remaining=3, services=[_service(marker_present=False)])
        self.assertEqual((broken["tone"], broken["action"]), ("err", None))
        self.assertIsNone(self._me(trust_days_remaining=None)["action"])


class TestMember(unittest.TestCase):
    def _them(self, member):
        return view.people(_status(household=[member]))[1]

    def test_every_stage(self):
        report = {
            "download": 1247,
            "unclaimed": 412,
            "deletes": True,
            "over_limit": False,
        }
        for member, tone, sentence, action in (
            (_member(saved=False), "idle", "Waiting for sign-in", "Send link"),
            (_member("review", report=report), "warn", "Ready for review", "Review"),
            (
                _member("checking"),
                "busy",
                "Checking what's already in the folder",
                None,
            ),
            (_member("syncing"), "busy", "Backing up now", None),
            (
                _member("ok", last_sync_relative="2 h ago", files_downloaded=5),
                "ok",
                "Backed up 2 h ago",
                None,
            ),
            (_member("ok"), "ok", "Backed up", None),
            (
                _member("needs_sign_in", detail="Apple wants the code."),
                "err",
                "Sign-in has run out",
                "Send link",
            ),
            (_member("blocked", detail="x"), "err", "Not backing up", "Open"),
            (_member("error", detail="x"), "err", "The last backup failed", "Open"),
            (_member(None), "idle", "First backup starts soon", None),
        ):
            them = self._them(member)
            self.assertEqual(
                (them["tone"], them["sentence"], (them["action"] or {}).get("label")),
                (tone, sentence, action),
                member,
            )
            self.assertEqual((them["name"], them["page"]), ("Alex", "/household/alex"))

    def test_review_detail(self):
        report = {
            "download": 1247,
            "unclaimed": 412,
            "deletes": True,
            "over_limit": False,
        }
        self.assertTrue(
            self._them(_member("review", report=report))["detail"].startswith("1,247 to download · 412 to delete."),
        )
        for kept in (
            {**report, "deletes": False},
            {**report, "over_limit": True},
            {**report, "unclaimed": 0},
        ):
            self.assertNotIn("to delete", self._them(_member("review", report=kept))["detail"])
        self.assertTrue(self._them(_member("review"))["detail"].startswith("0 to download."))

    def test_ok_detail(self):
        self.assertEqual(self._them(_member("ok", files_downloaded=5))["detail"], "5 new")
        self.assertEqual(
            self._them(_member("ok", files_downloaded=5, detail="Fine."))["detail"],
            "Fine.",
        )
        self.assertIsNone(self._them(_member("ok"))["detail"])


class TestHeadline(unittest.TestCase):
    def _title(self, **over):
        return view.headline(view.people(_status(**over)))["title"]

    def test_all_is_well(self):
        self.assertEqual(self._title(household=[_member("ok")]), "Everything is backed up")

    def test_what_to_do_about_the_main_account(self):
        self.assertEqual(self._title(auth_state="reauth_needed"), "Sign in again to restart backups")
        self.assertEqual(self._title(auth_state="setup_needed"), "Sign in to start backing up")
        self.assertEqual(self._title(auth_state=None), "Sign in to start backing up")
        self.assertEqual(self._title(trust_days_remaining=3), "Refresh trust: it runs out in 3 days")
        self.assertEqual(self._title(trust_days_remaining=1), "Refresh trust: it runs out in 1 day")
        self.assertEqual(self._title(trust_days_remaining=0), "Refresh trust to keep backups running")

    def test_a_member_named(self):
        for member, title in (
            (_member("review"), "Alex's backup is ready for review"),
            (_member("needs_sign_in"), "Alex needs to sign in again"),
            (_member("blocked"), "Alex's backup is not running"),
            (_member("error"), "Alex's last backup failed"),
            (_member(saved=False), "Waiting for Alex to sign in"),
            (_member(None), "Alex: first backup starts soon"),
        ):
            self.assertEqual(self._title(household=[member]), title)

    def test_the_worst_comes_first(self):
        title = self._title(trust_days_remaining=3, household=[_member("error")])
        self.assertEqual(title, "Alex's last backup failed")

    def test_busy(self):
        self.assertEqual(self._title(household=[_member("syncing")]), "Backing up")

    def test_waiting_on_the_main_account(self):
        self.assertEqual(self._title(services=[_service(stats=None)]), "Waiting for the first backup")

    def test_nobody(self):
        self.assertEqual(view.headline([])["title"], "Nothing set up yet")

    def test_refreshing(self):
        status = _status(
            auth_state="setup_needed",
            services=[_service(syncing_since_relative="1 min ago")],
        )
        self.assertTrue(view.refreshing(status, view.people(status)))
        status = _status(household=[_member("syncing")])
        self.assertTrue(view.refreshing(status, view.people(status)))
        status = _status()
        self.assertFalse(view.refreshing(status, view.people(status)))


class TestLogSummary(unittest.TestCase):
    def test_counts(self):
        info = "2026-11-09 22:05:34,241 :: INFO :: root :: x.py :: 1 :: fine"
        warn = "2026-11-09 22:05:34,241 :: WARNING :: root :: x.py :: 1 :: hm"
        err = "2026-11-09 22:05:34,241 :: ERROR :: root :: x.py :: 1 :: bad"
        self.assertEqual(view.log_summary([info])["text"], "Nothing unusual recently")
        self.assertEqual(view.log_summary(None)["errors"], 0)
        self.assertEqual(view.log_summary([warn])["text"], "1 warning recently")
        summary = view.log_summary([err, warn, warn, err, info])
        self.assertEqual(summary["text"], "2 errors and 2 warnings recently")
        self.assertEqual(summary["last"], err)
        self.assertEqual(view.log_summary([err])["text"], "1 error recently")

    def test_default_notices_are_not_problems(self):
        notice = (
            "2026-11-14 22:11:45,214 :: WARNING :: root :: config_logging.py :: 26 :: "
            "photos > filters > albums not found. Downloading all albums ..."
        )
        config_error = "2026-11-14 22:11:45,214 :: ERROR :: root :: config_logging.py :: 30 :: username is missing"
        self.assertEqual(view.log_summary([notice, notice])["text"], "Nothing unusual recently")
        self.assertIsNone(view.log_summary([notice])["top"])
        self.assertEqual(view.log_summary([notice, config_error])["text"], "1 error recently")
        misnested = (
            "2026-11-14 22:11:45,214 :: WARNING :: root :: config_logging.py :: 26 :: "
            "app > discord > webhook_url is not found; 'app > webhook_url' exists but must be nested"
        )
        self.assertEqual(view.log_summary([notice, misnested])["text"], "1 warning recently")

    def test_log_summary_says_what_the_errors_are_about(self):
        def line(level, logger, message):
            return f"2026-11-11 22:57:03,830 :: {level} :: {logger} :: x.py :: 89 :: {message}"

        lines = [
            line("ERROR", "icloudpy.base", "ObjectNotFoundException: Could not find document (NOT_FOUND)"),
            line("ERROR", "root", "File not found in iCloud Drive - /icloud/drive/A/one.mp4: ObjectNotFoundException"),
            line("ERROR", "root", "[alex] File not found in iCloud Drive - /icloud/drive/A/two.mp4: x"),
            line("ERROR", "root", "[alex] Refusing to remove 55905 of 61026 files (92%) under /icloud/photos/A"),
        ]
        summary = view.log_summary(lines)
        self.assertEqual(summary["errors"], 4)
        self.assertEqual(summary["top"], "Mostly: File not found in iCloud Drive (2)")
        self.assertEqual(view.log_summary(lines[3:])["top"], "Refusing to remove N of N files (1)")
        self.assertIsNone(view.log_summary(lines[:1])["top"])
        zone = line("WARNING", "root", "Skipping obsolete-file cleanup for SharedSync-0A1B2C3D-4E5F-6789: indexing")
        self.assertEqual(view.log_summary([zone])["top"], "Skipping obsolete-file cleanup for the Shared Library (1)")
