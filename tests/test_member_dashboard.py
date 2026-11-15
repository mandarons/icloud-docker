"""Tests for the household member's card and backup controls on the dashboard."""

import os
from unittest.mock import patch

import tests  # noqa: F401 - sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import accounts, member_sync, web, web_signals
from tests.test_photo_adopt import MEMBER, _config, _Dirs, _write
from tests.test_web import _csrf_post


class TestDashboard(_Dirs):
    def setUp(self):
        super().setUp()
        self.config = _config(self.root, {"id": "member", "username": MEMBER})
        patcher = patch.object(web, "_load_current_config", return_value=self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = web.create_app(testing=True).test_client()
        _write(os.path.join(accounts.cookie_directory("member"), "membersession"), 1)

    def _dashboard(self):
        bare = {key: value for key, value in self.config.items() if key not in ("drive", "photos")}
        with patch.object(web, "_load_current_config", return_value=bare):
            return self.client.get("/").get_data(as_text=True)

    def _set(self, **fields):
        with web_signals.as_account("member"):
            web_signals.record_member(**fields)

    def test_backup_summary(self):
        self.assertEqual(web._member_backup("member")["status"], "waiting")  # noqa: SLF001
        self._set(status="ok")
        with web_signals.as_account("member"):
            web_signals.record_sync_completion("photos", files_downloaded=2)
        backup = web._member_backup("member")  # noqa: SLF001
        self.assertEqual((backup["label"], backup["files_downloaded"]), ("backed up", 2))
        self.assertTrue(backup["last_sync_relative"])
        with web_signals.as_account("member"):
            web_signals.record_service_running("photos", running=True)
        self.assertEqual(web._member_backup("member")["status"], "syncing")  # noqa: SLF001
        self._set(report="junk")
        self.assertIsNone(web._member_backup("member")["report"])  # noqa: SLF001

    def test_report_and_start(self):
        report = {
            "assets": 10,
            "on_disk": 1,
            "old_name": 6,
            "download": 3,
            "download_by_year": {"2025": 2, "2026": 1},
            "unclaimed": 4,
            "folder": "member",
            "samples": {"download": ["2026/01/02/IMG_3.HEIC"], "unclaimed": []},
            "stopped": "boom",
        }
        self._set(status="review", report=report)
        dashboard = self._dashboard()
        self.assertIn("Ready for review", dashboard)
        self.assertIn("3 to download", dashboard)
        self.assertIn(">Review<", dashboard)
        page = self.client.get("/household/member").get_data(as_text=True)
        for text in (
            "Check stopped early",
            "7 files",
            "6 under older names",
            "3 files",
            "To download, 2025",
            "Start backup",
            "Check again",
            "IMG_3.HEIC",
            "partial",
        ):
            self.assertIn(text, page)

        with patch.object(member_sync, "wake") as wake:
            response = _csrf_post(self.client, "/household/member/start")
        wake.assert_called_once()
        self.assertTrue(response.headers["Location"].endswith("/household/member"))
        with web_signals.as_account("member"):
            self.assertTrue(web_signals.get_member()["approved"])
        page = self.client.get("/household/member").get_data(as_text=True)
        self.assertNotIn("Start backup", page)
        self.assertIn("Back up now", page)

    def test_recheck_sync_and_refusals(self):
        self._set(status="review", report={"assets": 1})
        with patch.object(member_sync, "wake") as wake:
            _csrf_post(self.client, "/household/member/recheck")
            _csrf_post(self.client, "/household/member/sync")
            self.assertEqual(self.client.post("/household/member/sync").status_code, 403)
            self.assertEqual(_csrf_post(self.client, "/household/nobody/sync").status_code, 302)
        self.assertEqual(wake.call_count, 2)
        with web_signals.as_account("member"):
            self.assertNotIn("report", web_signals.get_member())

    def test_ok_card_and_detail(self):
        self._set(status="ok", adopted=12, detail="All good.")
        with web_signals.as_account("member"):
            web_signals.record_sync_completion("photos", files_downloaded=1234)
        page = self.client.get("/household/member").get_data(as_text=True)
        self.assertIn("<dt>New last time</dt><dd>1,234</dd>", page)
        self.assertIn("<dt>Kept under older names</dt><dd>12</dd>", page)
        self.assertIn("All good.", page)
        dashboard = self._dashboard()
        self.assertIn("Backed up", dashboard)
        self.assertIn("All good.", dashboard)
