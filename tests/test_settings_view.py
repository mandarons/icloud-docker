"""Tests for the Settings page (``src.settings_view`` and ``/settings``)."""

import glob
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import tests  # noqa: F401 - sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import DEFAULT_CONFIG_FILE_PATH, ENV_ICLOUD_PASSWORD_KEY, config_parser, read_config, settings_view, web
from tests.test_web import _csrf_post

_CONFIG_WITH_COMMENTS = """\
app:
  # who signs in
  credentials:
    username: "user@example.com"
  root: "/icloud"
  telegram:
    bot_token: "123456:SECRET-TOKEN"
    chat_id: "424242"
drive:
  destination: "drive"
  # keep this comment
  sync_interval: 300
photos:
  destination: "photos"
  sync_interval: 500
"""


class TestDefaults(unittest.TestCase):
    """Defaults shown on the page are the ones the app really uses."""

    MINIMAL = {
        "app": {"credentials": {"username": "user@example.com"}},
        "drive": {},
        "photos": {},
    }

    GETTERS = {
        "app.region": config_parser.get_region,
        "app.credentials.retry_login_interval": config_parser.get_retry_login_interval,
        "app.trust_expiry_warn_days": config_parser.get_trust_expiry_warn_days,
        "app.trust_refresh_days": config_parser.get_trust_refresh_days,
        "app.root": config_parser.get_root_destination_path,
        "app.mount_marker_filename": config_parser.get_mount_marker_filename,
        "app.recycle_bin.enabled": config_parser.get_recycle_bin_enabled,
        "app.recycle_bin.retention_days": config_parser.get_recycle_bin_retention_days,
        "app.web_ui.host": config_parser.get_web_ui_host,
        "app.web_ui.port": config_parser.get_web_ui_port,
        "app.web_ui.public_url": config_parser.get_web_ui_public_url,
        "app.usage_tracking.enabled": config_parser.get_usage_tracking_enabled,
        "drive.destination": config_parser.get_drive_destination_path,
        "drive.sync_interval": config_parser.get_drive_sync_interval,
        "drive.remove_obsolete": config_parser.get_drive_remove_obsolete,
        "drive.flatten_packages": config_parser.get_drive_flatten_packages,
        "drive.require_mount_marker": config_parser.get_drive_require_mount_marker,
        "drive.request_timeout": config_parser.get_drive_request_timeout,
        "photos.destination": config_parser.get_photos_destination_path,
        "photos.sync_interval": config_parser.get_photos_sync_interval,
        "photos.remove_obsolete": config_parser.get_photos_remove_obsolete,
        "photos.obsolete_delete_limit_percent": config_parser.get_photos_obsolete_delete_limit_percent,
        "photos.all_albums": config_parser.get_photos_all_albums,
        "photos.use_hardlinks": config_parser.get_photos_use_hardlinks,
        "photos.folder_format": config_parser.get_photos_folder_format,
        "photos.filename_format": config_parser.get_photos_filename_format,
        "photos.file_format": config_parser.get_photos_file_format,
        "photos.variant_separator": config_parser.get_photos_variant_separator,
        "photos.preserve_originals_as_bak": config_parser.get_photos_preserve_originals_as_bak,
        "photos.require_mount_marker": config_parser.get_photos_require_mount_marker,
        "photos.request_timeout": config_parser.get_photos_request_timeout,
        "photos.enumeration_chunk_size": config_parser.get_photos_enumeration_chunk_size,
        "photos.filters.fallback_to_original": config_parser.get_photos_fallback_to_original,
        "app.notifications.sync_summary.enabled": config_parser.get_sync_summary_enabled,
        "app.notifications.sync_summary.on_success": config_parser.get_sync_summary_on_success,
        "app.notifications.sync_summary.on_error": config_parser.get_sync_summary_on_error,
        "app.notifications.sync_summary.min_downloads": config_parser.get_sync_summary_min_downloads,
        "app.telegram.listen": config_parser.get_telegram_listen_enabled,
    }

    def test_each_declared_default_matches_the_app(self):
        for key, getter in self.GETTERS.items():
            with self.subTest(key=key):
                self.assertEqual(
                    getter(config=self.MINIMAL),
                    settings_view.SETTINGS_BY_KEY[key].default,
                )

    def test_every_getter_key_is_on_the_page(self):
        self.assertLessEqual(set(self.GETTERS), set(settings_view.SETTINGS_BY_KEY))


class TestRows(unittest.TestCase):
    def _rows(self, config):
        return {row["key"]: row for row in settings_view.build_rows(config)}

    def test_value_from_file_is_marked_config_yaml(self):
        rows = self._rows({"drive": {"sync_interval": 300}})
        self.assertEqual(rows["drive.sync_interval"]["display"], "5 min")
        self.assertEqual(rows["drive.sync_interval"]["source"], "config.yaml")

    def test_missing_value_shows_the_default(self):
        rows = self._rows({"drive": {}})
        self.assertEqual(rows["drive.sync_interval"]["display"], "30 min")
        self.assertEqual(rows["drive.sync_interval"]["source"], "default")

    def test_intervals_read_as_people_say_them(self):
        cases = {
            3600: "1 h",
            86400: "1 day",
            172800: "2 days",
            90: "1 min 30 s",
            5400: "1 h 30 min",
            500: "8 min 20 s",
            -1: "Once",
        }
        for seconds, text in cases.items():
            with self.subTest(seconds=seconds):
                self.assertEqual(
                    self._rows({"photos": {"sync_interval": seconds}})["photos.sync_interval"]["display"],
                    text,
                )

    def test_alerts_row_names_the_channels_set_up(self):
        alerts = self._rows({"app": {"telegram": {"bot_token": "x"}, "smtp": {"email": "  "}, "discord": None}})[""]
        self.assertEqual((alerts["label"], alerts["display"]), ("Alerts", "Telegram"))
        self.assertEqual(self._rows({})[""]["display"], "None set")
        self.assertIn("Telegram under app.telegram (on)", alerts["note"])
        self.assertIn("Email under app.smtp,", alerts["note"])

    def test_a_few_rows_are_up_front(self):
        rows = settings_view.build_rows({})
        common = [row for row in rows if row["common"]]
        self.assertLessEqual(len(common), 9)
        self.assertIn("photos.sync_interval", {row["key"] for row in common})
        self.assertTrue(all(key in settings_view.SETTINGS_BY_KEY for key in settings_view.COMMON))

    def test_an_empty_section_counts_as_unset(self):
        rows = self._rows({"app": {"telegram": None}})
        self.assertEqual(rows["app.telegram.bot_token"]["display"], "not set")

    def test_secrets_are_reported_but_never_shown(self):
        rows = self._rows({"app": {"telegram": {"bot_token": "123456:SECRET-TOKEN"}}})
        row = rows["app.telegram.bot_token"]
        self.assertEqual(row["display"], "set")
        self.assertIsNone(row["value"])

    def test_lists_and_maps_read_plainly(self):
        rows = self._rows(
            {
                "photos": {
                    "library_destinations": {"PrimarySync": "me"},
                    "filters": {"file_sizes": ["original", "full"]},
                },
            },
        )
        self.assertEqual(rows["photos.library_destinations"]["display"], "PrimarySync → me")
        self.assertEqual(rows["photos.filters.file_sizes"]["display"], "original, full")

    def test_env_password_adds_a_row_without_the_value(self):
        with patch.dict(os.environ, {ENV_ICLOUD_PASSWORD_KEY: "hunter2"}):
            rows = self._rows({})
            env = {row["name"]: row for row in settings_view.build_environment()}
        self.assertEqual(rows["password"]["source"], "env")
        self.assertEqual(rows["password"]["display"], "set")
        self.assertEqual(env[ENV_ICLOUD_PASSWORD_KEY]["display"], "set")

    def test_environment_shows_plain_values(self):
        with patch.dict(os.environ, {"PUID": "1000", "TZ": "Europe/Paris"}):
            env = {row["name"]: row for row in settings_view.build_environment()}
        self.assertEqual(env["PUID"]["display"], "1000")
        self.assertEqual(env["PUID"]["source"], "env")
        self.assertEqual(env["TZ"]["display"], "Europe/Paris")

    def test_a_single_string_list_reads_as_itself(self):
        rows = self._rows({"photos": {"filters": {"libraries": "PrimarySync"}}})
        self.assertEqual(rows["photos.filters.libraries"]["display"], "PrimarySync")

    def test_config_path_falls_back_to_the_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENV_CONFIG_FILE_PATH", None)
            env = {row["name"]: row for row in settings_view.build_environment()}
        self.assertEqual(env["ENV_CONFIG_FILE_PATH"]["source"], "default")
        self.assertEqual(env["ENV_CONFIG_FILE_PATH"]["display"], DEFAULT_CONFIG_FILE_PATH)

    def test_only_safe_keys_are_editable(self):
        editable = {s.key for s in settings_view.SETTINGS if s.editable}
        for risky in (
            "drive.remove_obsolete",
            "photos.remove_obsolete",
            "photos.destination",
            "photos.filename_format",
            "photos.folder_format",
            "photos.all_albums",
            "photos.filters.file_sizes",
        ):
            self.assertNotIn(risky, editable)


class TestWriteSetting(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "config.yaml")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(_CONFIG_WITH_COMMENTS)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _text(self):
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_changes_the_value_and_keeps_comments(self):
        settings_view.write_setting(self.path, "drive.sync_interval", "900")
        text = self._text()
        self.assertIn("sync_interval: 900", text)
        self.assertIn("# keep this comment", text)
        self.assertIn("# who signs in", text)
        self.assertIn('bot_token: "123456:SECRET-TOKEN"', text)

    def test_backs_the_file_up_first(self):
        settings_view.write_setting(self.path, "drive.sync_interval", "900")
        backups = glob.glob(self.path + ".bak-*")
        self.assertEqual(len(backups), 1)
        with open(backups[0], encoding="utf-8") as f:
            self.assertEqual(f.read(), _CONFIG_WITH_COMMENTS)

    def test_an_unchanged_value_writes_nothing(self):
        settings_view.write_setting(self.path, "drive.sync_interval", "300")
        self.assertEqual(glob.glob(self.path + ".bak-*"), [])
        self.assertEqual(self._text(), _CONFIG_WITH_COMMENTS)

    def test_creates_missing_sections(self):
        settings_view.write_setting(self.path, "app.notifications.sync_summary.enabled", "on")
        config = read_config(config_path=self.path)
        self.assertIs(config["app"]["notifications"]["sync_summary"]["enabled"], True)

    def test_bool_off(self):
        settings_view.write_setting(self.path, "photos.use_hardlinks", "off")
        self.assertIn("use_hardlinks: false", self._text())

    def test_refuses_keys_that_are_not_editable(self):
        with self.assertRaises(settings_view.SettingError):
            settings_view.write_setting(self.path, "photos.remove_obsolete", "on")
        with self.assertRaises(settings_view.SettingError):
            settings_view.write_setting(self.path, "no.such.key", "1")
        self.assertEqual(self._text(), _CONFIG_WITH_COMMENTS)

    def test_refuses_bad_values(self):
        for key, value in (
            ("drive.sync_interval", "0"),
            ("drive.sync_interval", "soon"),
            ("app.notifications.sync_summary.min_downloads", "-1"),
            ("photos.use_hardlinks", "maybe"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(settings_view.SettingError):
                settings_view.write_setting(self.path, key, value)
        self.assertEqual(self._text(), _CONFIG_WITH_COMMENTS)

    def test_a_scalar_in_the_way_is_refused(self):
        before = _CONFIG_WITH_COMMENTS.replace("  root:", "  notifications: nope\n  root:")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(before)
        with self.assertRaises(settings_view.SettingError):
            settings_view.write_setting(self.path, "app.notifications.sync_summary.enabled", "on")
        self.assertEqual(self._text(), before)

    def test_parse_refuses_kinds_it_cannot_edit(self):
        with self.assertRaises(settings_view.SettingError):
            settings_view.parse_value(settings_view.SETTINGS_BY_KEY["photos.folder_format"], "%Y")

    def test_an_empty_file_is_refused(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("")
        with self.assertRaises(settings_view.SettingError):
            settings_view.write_setting(self.path, "drive.sync_interval", "900")

    def test_a_result_the_app_cannot_read_never_lands(self):
        with (
            patch.object(settings_view, "read_config", side_effect=ValueError("bad")),
            self.assertRaises(ValueError),
        ):
            settings_view.write_setting(self.path, "drive.sync_interval", "900")
        self.assertEqual(self._text(), _CONFIG_WITH_COMMENTS)
        self.assertEqual(sorted(n for n in os.listdir(self.dir) if n.startswith(".config-")), [])

    def test_keeps_file_permissions(self):
        os.chmod(self.path, 0o600)
        settings_view.write_setting(self.path, "drive.sync_interval", "900")
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_leaves_no_temp_file_behind(self):
        settings_view.write_setting(self.path, "drive.sync_interval", "900")
        self.assertEqual(sorted(n for n in os.listdir(self.dir) if n.startswith(".config-")), [])


class TestSettingsRoutes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "config.yaml")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(_CONFIG_WITH_COMMENTS)
        self.patcher = patch.object(web, "_current_config_path", return_value=self.path)
        self.patcher.start()
        self.client = web.create_app(testing=True).test_client()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_page_renders_values_and_sources(self):
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("drive.sync_interval", html)
        self.assertIn("config.yaml", html)
        self.assertIn("Environment", html)

    def test_page_puts_the_rest_under_advanced(self):
        html = self.client.get("/settings").get_data(as_text=True)
        up_front, advanced = html.split("<summary>Advanced</summary>")
        self.assertIn("Back up every", up_front)
        self.assertNotIn("Download threads", up_front)
        self.assertIn("Download threads", advanced)
        self.assertNotIn('class="advanced" open', html)
        page = self.client.get("/settings?saved=app.trust_refresh_days").get_data(as_text=True)
        self.assertIn('class="advanced" open', page)

    def test_page_never_contains_a_secret(self):
        html = self.client.get("/settings").get_data(as_text=True)
        self.assertNotIn("SECRET-TOKEN", html)
        self.assertNotIn("424242", html)

    def test_header_links_to_settings(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/settings"', html)

    def test_post_needs_csrf(self):
        response = self.client.post("/settings", data={"key": "drive.sync_interval", "value": "900"})
        self.assertEqual(response.status_code, 403)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), _CONFIG_WITH_COMMENTS)

    def test_post_saves_and_redirects(self):
        response = _csrf_post(self.client, "/settings", {"key": "drive.sync_interval", "value": "900"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=drive.sync_interval", response.headers["Location"])
        with open(self.path, encoding="utf-8") as f:
            self.assertIn("sync_interval: 900", f.read())
        page = self.client.get(response.headers["Location"]).get_data(as_text=True)
        self.assertIn("Saved iCloud Drive · Back up every", page)

    def test_an_unchecked_switch_turns_the_key_off(self):
        _csrf_post(self.client, "/settings", {"key": "photos.use_hardlinks", "value": "on"})
        _csrf_post(self.client, "/settings", {"key": "photos.use_hardlinks"})
        with open(self.path, encoding="utf-8") as f:
            self.assertIn("use_hardlinks: false", f.read())

    def test_bad_value_is_a_400_with_the_reason(self):
        response = _csrf_post(self.client, "/settings", {"key": "drive.sync_interval", "value": "0"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("0 is not allowed", response.get_data(as_text=True))

    def test_a_failed_write_is_a_500_and_keeps_the_page(self):
        with patch.object(settings_view, "write_setting", side_effect=OSError("read-only file system")):
            response = _csrf_post(self.client, "/settings", {"key": "drive.sync_interval", "value": "900"})
        self.assertEqual(response.status_code, 500)
        self.assertIn("read-only file system", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
