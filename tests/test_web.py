"""Tests for the embedded web UI (``src.web``).

The web UI is a small Flask app that runs in a daemon thread alongside
the sync loop. These tests use Flask's test client and never touch a
real socket. Mocks for icloudpy live in their own classes near the
auth-flow tests.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import unittest

import tests  # noqa: F401  — sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import web


class TestStatus(unittest.TestCase):
    """``/api/status`` returns the live payload that powers the dashboard
    and any external consumer."""

    def test_status_returns_503_when_config_missing(self):
        import os

        previous = os.environ.get("ENV_CONFIG_FILE_PATH")
        os.environ["ENV_CONFIG_FILE_PATH"] = "/nonexistent/config.yaml"
        try:
            client = web.create_app(testing=True).test_client()
            response = client.get("/api/status")
            self.assertEqual(response.status_code, 503)
            payload = response.get_json()
            self.assertFalse(payload["config_loaded"])
        finally:
            if previous is None:
                del os.environ["ENV_CONFIG_FILE_PATH"]
            else:
                os.environ["ENV_CONFIG_FILE_PATH"] = previous

    def test_status_payload_top_level(self):
        client = web.create_app(testing=True).test_client()
        response = client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["config_loaded"])
        self.assertEqual(payload["username"], "user@test.com")
        self.assertEqual(payload["region"], "global")
        self.assertEqual(payload["marker_filename"], ".mounted")

    def test_status_lists_photos_and_drive(self):
        client = web.create_app(testing=True).test_client()
        payload = client.get("/api/status").get_json()
        names = [s["name"] for s in payload["services"]]
        self.assertIn("Photos", names)
        self.assertIn("Drive", names)

    def test_status_service_shape(self):
        """Each service entry exposes destination + interval + marker info."""
        client = web.create_app(testing=True).test_client()
        payload = client.get("/api/status").get_json()
        for service in payload["services"]:
            self.assertIn("destination", service)
            self.assertIn("sync_interval_s", service)
            self.assertIn("require_mount_marker", service)
            self.assertIn("marker_present", service)
            self.assertIn("marker_path", service)
            self.assertTrue(service["marker_path"].endswith("/.mounted"))

    def test_status_marker_present_reflects_filesystem(self):
        """Touching a marker file inside the destination flips marker_present."""
        import os
        import tempfile

        from src import read_config

        tmpdir = tempfile.mkdtemp()
        try:
            cfg_path = os.path.join(tmpdir, "config.yaml")
            with open("./tests/data/test_config.yaml") as src_cfg:
                content = src_cfg.read()
            # Repoint root so destinations land in the tmpdir.
            content = content.replace(
                'root: "./icloud"',
                f'root: "{tmpdir}/icloud"',
            )
            with open(cfg_path, "w") as f:
                f.write(content)

            previous = os.environ.get("ENV_CONFIG_FILE_PATH")
            os.environ["ENV_CONFIG_FILE_PATH"] = cfg_path
            try:
                # Find the photos destination the config_parser will compute.
                from src import config_parser

                cfg = read_config(config_path=cfg_path)
                photos_dest = config_parser.prepare_photos_destination(config=cfg)

                client = web.create_app(testing=True).test_client()
                before = client.get("/api/status").get_json()
                photos = [s for s in before["services"] if s["name"] == "Photos"][0]
                self.assertFalse(photos["marker_present"])

                open(os.path.join(photos_dest, ".mounted"), "w").close()

                after = client.get("/api/status").get_json()
                photos = [s for s in after["services"] if s["name"] == "Photos"][0]
                self.assertTrue(photos["marker_present"])
            finally:
                if previous is None:
                    del os.environ["ENV_CONFIG_FILE_PATH"]
                else:
                    os.environ["ENV_CONFIG_FILE_PATH"] = previous
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


class TestWebUiConfig(unittest.TestCase):
    """``config_parser.get_web_ui_{enabled,host,port}`` helpers — opt-in,
    default OFF so vanilla mandarons installs don't suddenly open port 8080."""

    def test_enabled_default_false(self):
        from src import config_parser

        self.assertFalse(config_parser.get_web_ui_enabled(config={}))
        self.assertFalse(config_parser.get_web_ui_enabled(config={"app": {}}))

    def test_enabled_true_when_set(self):
        from src import config_parser

        self.assertTrue(
            config_parser.get_web_ui_enabled(config={"app": {"web_ui": {"enabled": True}}}),
        )

    def test_host_default(self):
        from src import config_parser

        self.assertEqual(config_parser.get_web_ui_host(config={}), "0.0.0.0")  # noqa: S104

    def test_host_when_configured(self):
        from src import config_parser

        self.assertEqual(
            config_parser.get_web_ui_host(config={"app": {"web_ui": {"host": "127.0.0.1"}}}),
            "127.0.0.1",
        )

    def test_port_default(self):
        from src import config_parser

        self.assertEqual(config_parser.get_web_ui_port(config={}), 8080)

    def test_port_when_configured(self):
        from src import config_parser

        self.assertEqual(
            config_parser.get_web_ui_port(config={"app": {"web_ui": {"port": 9090}}}),
            9090,
        )


class TestMainRun(unittest.TestCase):
    """``main.run`` should start the web thread only when
    ``app.web_ui.enabled`` is True, then call ``sync.sync()``."""

    def test_run_starts_web_thread_when_enabled(self):
        import os
        import tempfile
        from unittest.mock import patch

        tmpdir = tempfile.mkdtemp()
        try:
            cfg_path = os.path.join(tmpdir, "config.yaml")
            with open("./tests/data/test_config.yaml") as src_cfg:
                content = src_cfg.read()
            # Inject the web_ui block.
            content = content.replace(
                "app:\n",
                "app:\n  web_ui:\n    enabled: true\n    port: 9999\n",
                1,
            )
            with open(cfg_path, "w") as f:
                f.write(content)

            previous = os.environ.get("ENV_CONFIG_FILE_PATH")
            os.environ["ENV_CONFIG_FILE_PATH"] = cfg_path
            try:
                from src import main

                with patch("src.web.start_in_thread") as start, patch("src.sync.sync"):
                    main.run()
                start.assert_called_once_with(host="0.0.0.0", port=9999)
            finally:
                if previous is None:
                    del os.environ["ENV_CONFIG_FILE_PATH"]
                else:
                    os.environ["ENV_CONFIG_FILE_PATH"] = previous
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_run_skips_web_thread_when_disabled(self):
        """Default config (no app.web_ui block) -> web thread NOT started."""
        from unittest.mock import patch

        from src import main

        with (
            patch("src.web.start_in_thread") as start,
            patch("src.sync.sync") as sync_mock,
        ):
            main.run()
        start.assert_not_called()
        sync_mock.assert_called_once()

    def test_run_skips_web_thread_when_partial_config(self):
        """Partial config (e.g. missing app.credentials block) -> web
        thread NOT started, but sync.sync is still called. The sync
        loop has its own retry/recovery for malformed configs."""
        import os
        import tempfile
        from unittest.mock import patch

        tmpdir = tempfile.mkdtemp()
        try:
            cfg_path = os.path.join(tmpdir, "config.yaml")
            with open(cfg_path, "w") as f:
                f.write("app:\n  logger:\n    filename: ./icloud.log\n")
            previous = os.environ.get("ENV_CONFIG_FILE_PATH")
            os.environ["ENV_CONFIG_FILE_PATH"] = cfg_path
            try:
                from src import main

                with (
                    patch("src.web.start_in_thread") as start,
                    patch("src.sync.sync") as sync_mock,
                ):
                    main.run()
                start.assert_not_called()
                sync_mock.assert_called_once()
            finally:
                if previous is None:
                    del os.environ["ENV_CONFIG_FILE_PATH"]
                else:
                    os.environ["ENV_CONFIG_FILE_PATH"] = previous
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)


class TestAuthForm(unittest.TestCase):
    """``GET /auth`` renders the form. Two states controlled by the
    module-level ``_PENDING_AUTH`` dict: password-only (default) and
    code-only (after a successful password POST that triggered 2FA)."""

    def setUp(self):
        """Ensure no pending auth leaks across tests."""
        with web._AUTH_LOCK:
            web._PENDING_AUTH.clear()

    def test_auth_get_returns_200(self):
        client = web.create_app(testing=True).test_client()
        response = client.get("/auth")
        self.assertEqual(response.status_code, 200)

    def test_auth_renders_password_field_when_no_pending(self):
        client = web.create_app(testing=True).test_client()
        body = client.get("/auth").data.decode("utf-8")
        self.assertIn('name="password"', body)
        self.assertIn('action="/auth/password"', body)

    def test_auth_renders_code_field_when_pending(self):
        with web._AUTH_LOCK:
            web._PENDING_AUTH["api"] = object()
            web._PENDING_AUTH["username"] = "user@test.com"
        try:
            client = web.create_app(testing=True).test_client()
            body = client.get("/auth").data.decode("utf-8")
            self.assertIn('name="code"', body)
            self.assertIn('action="/auth/code"', body)
        finally:
            with web._AUTH_LOCK:
                web._PENDING_AUTH.clear()


class TestAuthPasswordPost(unittest.TestCase):
    """``POST /auth/password`` resolves the username from config, builds a
    fresh ``ICloudPyService``, optionally fires the 2FA push, and stashes
    the live session for ``POST /auth/code``."""

    def setUp(self):
        with web._AUTH_LOCK:
            web._PENDING_AUTH.clear()

    def tearDown(self):
        with web._AUTH_LOCK:
            web._PENDING_AUTH.clear()

    def test_empty_password_returns_400(self):
        client = web.create_app(testing=True).test_client()
        response = client.post("/auth/password", data={"password": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Password is required", response.data)

    def test_no_username_in_config_returns_400(self):
        import os
        import tempfile

        tmpdir = tempfile.mkdtemp()
        try:
            cfg_path = os.path.join(tmpdir, "config.yaml")
            # Minimal config with no app.credentials.username.
            with open(cfg_path, "w") as f:
                f.write("app:\n  logger:\n    filename: ./icloud.log\n")
            previous = os.environ.get("ENV_CONFIG_FILE_PATH")
            os.environ["ENV_CONFIG_FILE_PATH"] = cfg_path
            try:
                client = web.create_app(testing=True).test_client()
                response = client.post("/auth/password", data={"password": "x"})
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"app.credentials.username", response.data)
            finally:
                if previous is None:
                    del os.environ["ENV_CONFIG_FILE_PATH"]
                else:
                    os.environ["ENV_CONFIG_FILE_PATH"] = previous
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_2fa_required_stashes_api_and_triggers_push(self):
        """When ICloudPyService.requires_2fa is True, we stash the api +
        redirect to /auth (now showing the code form), AND we call
        trigger_2fa_push_notification if the helper is available."""
        from unittest.mock import MagicMock, patch

        fake_api = MagicMock()
        fake_api.requires_2fa = True
        fake_api.trigger_2fa_push_notification = MagicMock(return_value=True)

        with (
            patch("icloudpy.ICloudPyService", return_value=fake_api),
            patch("icloudpy.utils.store_password_in_keyring"),
        ):
            client = web.create_app(testing=True).test_client()
            response = client.post("/auth/password", data={"password": "x"})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/auth"))
        fake_api.trigger_2fa_push_notification.assert_called_once()
        with web._AUTH_LOCK:
            self.assertIn("api", web._PENDING_AUTH)
            self.assertEqual(web._PENDING_AUTH["username"], "user@test.com")

    def test_no_2fa_required_stores_keyring_and_redirects(self):
        """Resumed-session case: ICloudPyService picks up the existing
        trusted-session cookie, returns requires_2fa=False, and we just
        persist the password to the keyring and redirect to /."""
        from unittest.mock import MagicMock, patch

        fake_api = MagicMock()
        fake_api.requires_2fa = False

        with (
            patch("icloudpy.ICloudPyService", return_value=fake_api),
            patch("icloudpy.utils.store_password_in_keyring") as keyring,
        ):
            client = web.create_app(testing=True).test_client()
            response = client.post("/auth/password", data={"password": "secret"})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/"))
        keyring.assert_called_once_with(username="user@test.com", password="secret")
        with web._AUTH_LOCK:
            self.assertNotIn("api", web._PENDING_AUTH)

    def test_authentication_exception_renders_error(self):
        """ICloudPyService raising — rendered as error pill, no crash."""
        from unittest.mock import patch

        with patch("icloudpy.ICloudPyService", side_effect=RuntimeError("Apple said no")):
            client = web.create_app(testing=True).test_client()
            response = client.post("/auth/password", data={"password": "x"})

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Apple said no", response.data)


class TestAuthCodePost(unittest.TestCase):
    """``POST /auth/code`` validates the 6-digit code on the stashed live
    session, trusts the browser, persists the password, clears pending,
    and redirects."""

    def setUp(self):
        with web._AUTH_LOCK:
            web._PENDING_AUTH.clear()

    def tearDown(self):
        with web._AUTH_LOCK:
            web._PENDING_AUTH.clear()

    def test_empty_code_returns_400(self):
        with web._AUTH_LOCK:
            web._PENDING_AUTH["api"] = object()
            web._PENDING_AUTH["username"] = "user@test.com"
            web._PENDING_AUTH["password"] = "secret"
        client = web.create_app(testing=True).test_client()
        response = client.post("/auth/code", data={"code": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Enter the 6-digit code", response.data)

    def test_no_pending_auth_returns_400(self):
        client = web.create_app(testing=True).test_client()
        response = client.post("/auth/code", data={"code": "123456"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"No pending auth", response.data)

    def test_rejected_code_returns_400(self):
        from unittest.mock import MagicMock

        fake_api = MagicMock()
        fake_api.validate_2fa_code.return_value = False
        with web._AUTH_LOCK:
            web._PENDING_AUTH["api"] = fake_api
            web._PENDING_AUTH["username"] = "user@test.com"
            web._PENDING_AUTH["password"] = "secret"

        client = web.create_app(testing=True).test_client()
        response = client.post("/auth/code", data={"code": "000000"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Code rejected", response.data)
        # Pending preserved so user can retry.
        with web._AUTH_LOCK:
            self.assertIn("api", web._PENDING_AUTH)

    def test_accepted_code_trusts_persists_clears_redirects(self):
        from unittest.mock import MagicMock, patch

        fake_api = MagicMock()
        fake_api.validate_2fa_code.return_value = True
        with web._AUTH_LOCK:
            web._PENDING_AUTH["api"] = fake_api
            web._PENDING_AUTH["username"] = "user@test.com"
            web._PENDING_AUTH["password"] = "secret"

        with patch("icloudpy.utils.store_password_in_keyring") as keyring:
            client = web.create_app(testing=True).test_client()
            response = client.post("/auth/code", data={"code": "123456"})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/"))
        fake_api.validate_2fa_code.assert_called_once_with("123456")
        fake_api.trust_session.assert_called_once()
        keyring.assert_called_once_with(username="user@test.com", password="secret")
        # Pending cleared.
        with web._AUTH_LOCK:
            self.assertNotIn("api", web._PENDING_AUTH)

    def test_trust_session_failure_still_succeeds(self):
        """trust_session() raising is non-fatal — the code already worked,
        we should still redirect + clear pending. Just log a warning."""
        from unittest.mock import MagicMock, patch

        fake_api = MagicMock()
        fake_api.validate_2fa_code.return_value = True
        fake_api.trust_session.side_effect = RuntimeError("cookie write failed")
        with web._AUTH_LOCK:
            web._PENDING_AUTH["api"] = fake_api
            web._PENDING_AUTH["username"] = "user@test.com"
            web._PENDING_AUTH["password"] = "secret"

        with patch("icloudpy.utils.store_password_in_keyring"):
            client = web.create_app(testing=True).test_client()
            response = client.post("/auth/code", data={"code": "123456"})

        self.assertEqual(response.status_code, 302)
        with web._AUTH_LOCK:
            self.assertNotIn("api", web._PENDING_AUTH)


class TestAuthReset(unittest.TestCase):
    """``POST /auth/reset`` is the escape hatch — clears _PENDING_AUTH so
    the form returns to the password state."""

    def test_reset_clears_pending(self):
        with web._AUTH_LOCK:
            web._PENDING_AUTH["api"] = object()
            web._PENDING_AUTH["username"] = "user@test.com"

        client = web.create_app(testing=True).test_client()
        response = client.post("/auth/reset")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/auth"))
        with web._AUTH_LOCK:
            self.assertNotIn("api", web._PENDING_AUTH)


class TestDashboard(unittest.TestCase):
    """``GET /`` renders the dashboard HTML — Apple-leaning design baked
    into ``base.html`` + ``dashboard.html``."""

    def test_dashboard_returns_200(self):
        client = web.create_app(testing=True).test_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_contains_brand(self):
        client = web.create_app(testing=True).test_client()
        body = client.get("/").data.decode("utf-8")
        self.assertIn("iCloud Docker", body)

    def test_dashboard_contains_username(self):
        client = web.create_app(testing=True).test_client()
        body = client.get("/").data.decode("utf-8")
        self.assertIn("user@test.com", body)

    def test_dashboard_renders_both_service_cards(self):
        client = web.create_app(testing=True).test_client()
        body = client.get("/").data.decode("utf-8")
        self.assertIn("Photos", body)
        self.assertIn("Drive", body)

    def test_dashboard_has_log_section(self):
        client = web.create_app(testing=True).test_client()
        body = client.get("/").data.decode("utf-8")
        self.assertIn("Recent log", body)


class TestLogs(unittest.TestCase):
    """``/api/logs`` returns the last N lines of the log file the running
    ``sync.py`` is writing to. Best-effort: missing or unreadable files
    return an empty list and never 500."""

    def test_logs_returns_lines_array(self):
        client = web.create_app(testing=True).test_client()
        response = client.get("/api/logs")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("lines", payload)
        self.assertIsInstance(payload["lines"], list)

    def test_logs_returns_empty_when_log_file_missing(self):
        import os
        import tempfile

        tmpdir = tempfile.mkdtemp()
        try:
            cfg_path = os.path.join(tmpdir, "config.yaml")
            with open("./tests/data/test_config.yaml") as src_cfg:
                content = src_cfg.read()
            # Point the logger at a file that doesn't exist.
            content = content.replace("filename: icloud.log", "filename: /nonexistent/icloud.log")
            with open(cfg_path, "w") as f:
                f.write(content)
            previous = os.environ.get("ENV_CONFIG_FILE_PATH")
            os.environ["ENV_CONFIG_FILE_PATH"] = cfg_path
            try:
                client = web.create_app(testing=True).test_client()
                response = client.get("/api/logs")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json(), {"lines": []})
            finally:
                if previous is None:
                    del os.environ["ENV_CONFIG_FILE_PATH"]
                else:
                    os.environ["ENV_CONFIG_FILE_PATH"] = previous
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_logs_tails_last_n_lines(self):
        """Direct test of the ``_tail_log_file`` helper."""
        import os
        import tempfile

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".log") as f:
            for i in range(500):
                f.write(f"line {i}\n")
            path = f.name
        try:
            tail = web._tail_log_file(path=path, lines=10)
            self.assertEqual(len(tail), 10)
            self.assertEqual(tail[-1], "line 499")
            self.assertEqual(tail[0], "line 490")
        finally:
            os.unlink(path)


class TestNoCacheHeaders(unittest.TestCase):
    """Every response gets ``Cache-Control: no-store`` (defense against
    Cloudflare / browser BFCache / mobile-carrier proxies serving a stale
    dashboard or auth payload)."""

    def test_dashboard_response_is_no_store(self):
        client = web.create_app(testing=True).test_client()
        response = client.get("/")
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))

    def test_api_response_is_no_store(self):
        client = web.create_app(testing=True).test_client()
        response = client.get("/api/status")
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))


class TestHealth(unittest.TestCase):
    """``/api/health`` is the tiny endpoint external monitors (UptimeRobot)
    can hit. 200 when the configured config file is readable; 503 when it
    is missing."""

    def test_health_returns_ok_when_config_loads(self):
        client = web.create_app(testing=True).test_client()
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"state": "ok"})

    def test_health_returns_503_when_config_missing(self):
        import os

        previous = os.environ.get("ENV_CONFIG_FILE_PATH")
        os.environ["ENV_CONFIG_FILE_PATH"] = "/nonexistent/config.yaml"
        try:
            client = web.create_app(testing=True).test_client()
            response = client.get("/api/health")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.get_json(), {"state": "config_missing"})
        finally:
            if previous is None:
                del os.environ["ENV_CONFIG_FILE_PATH"]
            else:
                os.environ["ENV_CONFIG_FILE_PATH"] = previous


if __name__ == "__main__":
    unittest.main()
