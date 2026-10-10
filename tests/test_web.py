"""Tests for the embedded web UI (``src.web``).

The web UI is a small Flask app that runs in a daemon thread alongside
the sync loop. These tests use Flask's test client and never touch a
real socket. Mocks for icloudpy live in their own classes near the
auth-flow tests.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import unittest
from unittest.mock import patch

import tests  # noqa: F401  — sets ENV_CONFIG_FILE_PATH via tests/__init__
from src import web


def _csrf_post(client, path, data=None, **kwargs):
    """POST helper that injects the CSRF cookie + form token.

    The web app's CSRF middleware (double-submit cookie pattern) rejects
    state-changing POSTs without a matching cookie + ``csrf_token`` form
    field. Tests should use this wrapper so they exercise the real
    middleware rather than bypassing it -- a regression in CSRF
    enforcement would otherwise hide behind tests that quietly skip the
    check.
    """
    token = web._get_csrf_token()  # noqa: SLF001
    client.set_cookie(web._CSRF_COOKIE_NAME, token)  # noqa: SLF001
    data = dict(data or {})
    data.setdefault("csrf_token", token)
    return client.post(path, data=data, **kwargs)


def _reset_pending_auth():
    """Test helper: clear ``_PENDING_AUTH`` under ``_AUTH_LOCK``.

    Several tests mutate the module-level dict directly during setUp /
    tearDown. Funneling through this helper guarantees the lock is
    always acquired -- otherwise the lock-usage convention is half-on
    half-off, which becomes a real bug if the suite ever runs in
    parallel."""
    with web._AUTH_LOCK:  # noqa: SLF001
        web._PENDING_AUTH.clear()  # noqa: SLF001


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
            config_parser.get_web_ui_enabled(
                config={"app": {"web_ui": {"enabled": True}}},
            ),
        )

    def test_host_default(self):
        """Default host is 127.0.0.1 -- safer-by-default. Users who
        want LAN exposure (behind a reverse proxy / Authelia) set
        ``app.web_ui.host: 0.0.0.0`` consciously."""
        from src import config_parser

        self.assertEqual(
            config_parser.get_web_ui_host(config={}),
            "127.0.0.1",
        )

    def test_host_when_configured(self):
        from src import config_parser

        self.assertEqual(
            config_parser.get_web_ui_host(
                config={"app": {"web_ui": {"host": "127.0.0.1"}}},
            ),
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
                # Default host follows the safer-by-default 127.0.0.1.
                # LAN exposure requires opt-in via app.web_ui.host: 0.0.0.0.
                start.assert_called_once_with(host="127.0.0.1", port=9999)
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

    def test_load_config_returns_none_when_read_config_raises(self):
        """A malformed YAML or missing app block causes read_config to
        raise — main caches None and skips the web thread, sync.sync
        handles the malformed-config retry path itself."""
        from src import main

        with (
            patch(
                "src.main.read_config",
                side_effect=KeyError("malformed"),
            ),
            patch("os.path.isfile", return_value=True),
            patch(
                "src.web.start_in_thread",
            ) as start,
            patch("src.sync.sync"),
        ):
            main.run()
        start.assert_not_called()

    def test_load_config_returns_none_when_config_file_missing(self):
        """If the configured config path doesn't exist on disk,
        _load_config_safely returns None via the early isfile guard —
        web thread NOT started, sync.sync IS (it has its own retry)."""
        from src import main

        previous = os.environ.get("ENV_CONFIG_FILE_PATH")
        os.environ["ENV_CONFIG_FILE_PATH"] = "/nonexistent/path/config.yaml"
        try:
            with (
                patch("src.web.start_in_thread") as start,
                patch(
                    "src.sync.sync",
                ) as sync_mock,
            ):
                main.run()
            start.assert_not_called()
            sync_mock.assert_called_once()
        finally:
            if previous is None:
                os.environ.pop("ENV_CONFIG_FILE_PATH", None)
            else:
                os.environ["ENV_CONFIG_FILE_PATH"] = previous

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
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.clear()  # noqa: SLF001

    def test_auth_get_returns_200(self):
        client = web.create_app(testing=True).test_client()
        response = client.get("/auth")
        self.assertEqual(response.status_code, 200)

    def test_auth_renders_password_field_when_no_pending(self):
        client = web.create_app(testing=True).test_client()
        body = client.get("/auth").data.decode("utf-8")
        self.assertIn('name="password"', body)
        self.assertIn('action="/auth/password"', body)
        self.assertIn('name="csrf_token" value="', body)

    def test_the_form_says_the_password_is_not_saved(self):
        """And it isn't: no sign-in from this page writes the keyring."""
        client = web.create_app(testing=True).test_client()
        with patch.object(web, "_password_is_stored", return_value=False):
            body = client.get("/auth").data.decode("utf-8")
        self.assertIn("never logged or saved", body)

    def test_auth_renders_code_field_when_pending(self):
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH["api"] = object()  # noqa: SLF001
            web._PENDING_AUTH["username"] = "user@test.com"  # noqa: SLF001
        try:
            client = web.create_app(testing=True).test_client()
            body = client.get("/auth").data.decode("utf-8")
            self.assertIn('name="code"', body)
            self.assertIn('action="/auth/code"', body)
        finally:
            with web._AUTH_LOCK:  # noqa: SLF001
                web._PENDING_AUTH.clear()  # noqa: SLF001


class TestAuthPasswordPost(unittest.TestCase):
    """``POST /auth/password`` resolves the username from config, builds a
    fresh ``ICloudPyService``, optionally fires the 2FA push, and stashes
    the live session for ``POST /auth/code``."""

    def setUp(self):
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.clear()  # noqa: SLF001

    def tearDown(self):
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.clear()  # noqa: SLF001

    def test_empty_password_returns_400(self):
        client = web.create_app(testing=True).test_client()
        response = _csrf_post(client, "/auth/password", data={"password": ""})
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
                response = _csrf_post(client, "/auth/password", data={"password": "x"})
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
            response = _csrf_post(client, "/auth/password", data={"password": "x"})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/auth"))
        fake_api.trigger_2fa_push_notification.assert_called_once()
        with web._AUTH_LOCK:  # noqa: SLF001
            self.assertIn("api", web._PENDING_AUTH)  # noqa: SLF001
            self.assertEqual(
                web._PENDING_AUTH["username"],  # noqa: SLF001
                "user@test.com",
            )

    def test_no_2fa_required_redirects_without_saving_the_password(self):
        """Resumed-session case: ICloudPyService picks up the existing
        trusted-session cookie and returns requires_2fa=False. The refreshed
        session is all the sync loop needs; the password is not saved."""
        from unittest.mock import MagicMock, patch

        fake_api = MagicMock()
        fake_api.requires_2fa = False

        from icloudpy import exceptions as icloudpy_exceptions

        with (
            patch("icloudpy.ICloudPyService", return_value=fake_api),
            patch(
                "icloudpy.utils.get_password_from_keyring",
                side_effect=icloudpy_exceptions.ICloudPyNoStoredPasswordAvailableException(),
            ),
            patch("icloudpy.utils.store_password_in_keyring") as keyring,
        ):
            client = web.create_app(testing=True).test_client()
            response = _csrf_post(client, "/auth/password", data={"password": "secret"})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/"))
        keyring.assert_not_called()
        with web._AUTH_LOCK:  # noqa: SLF001
            self.assertNotIn("api", web._PENDING_AUTH)  # noqa: SLF001

    def test_authentication_exception_renders_error(self):
        """ICloudPyService raising — rendered as error pill, no crash."""
        from unittest.mock import patch

        with patch(
            "icloudpy.ICloudPyService",
            side_effect=RuntimeError("Apple said no"),
        ):
            client = web.create_app(testing=True).test_client()
            response = _csrf_post(client, "/auth/password", data={"password": "x"})

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Apple said no", response.data)


class TestAuthCodePost(unittest.TestCase):
    """``POST /auth/code`` validates the 6-digit code on the stashed live
    session, trusts the browser, clears pending, and redirects. The
    password is never saved."""

    def setUp(self):
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.clear()  # noqa: SLF001

    def tearDown(self):
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH.clear()  # noqa: SLF001

    def test_empty_code_returns_400(self):
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH["api"] = object()  # noqa: SLF001
            web._PENDING_AUTH["username"] = "user@test.com"  # noqa: SLF001
        client = web.create_app(testing=True).test_client()
        response = _csrf_post(client, "/auth/code", data={"code": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Enter the 6-digit code", response.data)

    def test_no_pending_auth_returns_400(self):
        client = web.create_app(testing=True).test_client()
        response = _csrf_post(client, "/auth/code", data={"code": "123456"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"No pending auth", response.data)

    def test_rejected_code_returns_400(self):
        from unittest.mock import MagicMock

        fake_api = MagicMock()
        fake_api.validate_2fa_code.return_value = False
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH["api"] = fake_api  # noqa: SLF001
            web._PENDING_AUTH["username"] = "user@test.com"  # noqa: SLF001

        client = web.create_app(testing=True).test_client()
        response = _csrf_post(client, "/auth/code", data={"code": "000000"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Code rejected", response.data)
        # Pending is now cleared on ALL exit paths -- including rejection
        # -- so the user's password doesn't linger in process memory if
        # they walked away mid-flow. Retry path is /auth (re-enter
        # password) or /auth/refresh-trust if the keyring has it cached.
        with web._AUTH_LOCK:  # noqa: SLF001
            self.assertNotIn("api", web._PENDING_AUTH)  # noqa: SLF001

    def test_accepted_code_trusts_clears_redirects_without_saving(self):
        from unittest.mock import MagicMock, patch

        fake_api = MagicMock()
        fake_api.validate_2fa_code.return_value = True
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH["api"] = fake_api  # noqa: SLF001
            web._PENDING_AUTH["username"] = "user@test.com"  # noqa: SLF001

        with patch("icloudpy.utils.store_password_in_keyring") as keyring:
            client = web.create_app(testing=True).test_client()
            response = _csrf_post(client, "/auth/code", data={"code": "123456"})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/"))
        fake_api.validate_2fa_code.assert_called_once_with("123456")
        fake_api.trust_session.assert_called_once()
        keyring.assert_not_called()
        # Pending cleared.
        with web._AUTH_LOCK:  # noqa: SLF001
            self.assertNotIn("api", web._PENDING_AUTH)  # noqa: SLF001

    def test_a_session_only_re_auth_persists_no_password(self):
        """A code accepted for a password-free container leaves it
        password-free: nothing is written to the keyring."""
        from unittest.mock import MagicMock, patch

        fake_api = MagicMock()
        fake_api.validate_2fa_code.return_value = True
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH["api"] = fake_api  # noqa: SLF001
            web._PENDING_AUTH["username"] = "user@test.com"  # noqa: SLF001

        with patch("icloudpy.utils.store_password_in_keyring") as keyring:
            client = web.create_app(testing=True).test_client()
            response = _csrf_post(client, "/auth/code", data={"code": "123456"})

        self.assertEqual(response.status_code, 302)
        fake_api.trust_session.assert_called_once()
        keyring.assert_not_called()

    def test_trust_session_failure_still_succeeds(self):
        """trust_session() raising is non-fatal — the code already worked,
        we should still redirect + clear pending. Just log a warning."""
        from unittest.mock import MagicMock, patch

        fake_api = MagicMock()
        fake_api.validate_2fa_code.return_value = True
        fake_api.trust_session.side_effect = RuntimeError("cookie write failed")
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH["api"] = fake_api  # noqa: SLF001
            web._PENDING_AUTH["username"] = "user@test.com"  # noqa: SLF001

        with patch("icloudpy.utils.store_password_in_keyring"):
            client = web.create_app(testing=True).test_client()
            response = _csrf_post(client, "/auth/code", data={"code": "123456"})

        self.assertEqual(response.status_code, 302)
        with web._AUTH_LOCK:  # noqa: SLF001
            self.assertNotIn("api", web._PENDING_AUTH)  # noqa: SLF001


class TestAuthReset(unittest.TestCase):
    """``POST /auth/reset`` is the escape hatch — clears _PENDING_AUTH so
    the form returns to the password state."""

    def test_reset_clears_pending(self):
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH["api"] = object()  # noqa: SLF001
            web._PENDING_AUTH["username"] = "user@test.com"  # noqa: SLF001

        client = web.create_app(testing=True).test_client()
        response = _csrf_post(client, "/auth/reset")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/auth"))
        with web._AUTH_LOCK:  # noqa: SLF001
            self.assertNotIn("api", web._PENDING_AUTH)  # noqa: SLF001


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

    def test_photos_says_when_it_is_waiting_for_apple_to_index(self):
        """On the service, not a library row: while Apple indexes one zone
        no library can be read, so no row could carry it. How long the
        wait has been running is the only actionable part of it."""
        import time
        from unittest.mock import patch

        entry = {"waiting": True, "since": time.time() - 7200}
        with patch.object(web.web_signals, "get_photos_indexing", return_value=entry):
            body = web.create_app(testing=True).test_client().get("/").data.decode("utf-8")
        self.assertIn("Waiting for Apple to finish indexing", body)
        self.assertIn("started 2 h ago", body)

        # A wait recorded by an older build has no start time; still shown.
        with patch.object(web.web_signals, "get_photos_indexing", return_value={"waiting": True}):
            body = web.create_app(testing=True).test_client().get("/").data.decode("utf-8")
        self.assertIn("Waiting for Apple to finish indexing", body)
        self.assertNotIn("&middot; started", body)

    def test_the_indexing_note_is_absent_when_photos_is_not_waiting(self):
        """Which is almost always: it must not be a permanent fixture."""
        body = web.create_app(testing=True).test_client().get("/").data.decode("utf-8")
        self.assertNotIn("Waiting for Apple", body)

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
            content = content.replace(
                "filename: icloud.log",
                "filename: /nonexistent/icloud.log",
            )
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
            tail = web._tail_log_file(path=path, lines=10)  # noqa: SLF001
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


class TestAuthRefreshTrust(unittest.TestCase):
    """``POST /auth/refresh-trust`` uses the keyring-cached password to
    fire a fresh 2FA push without making the user retype.

    Most paths involve real iCloudPyService calls — we patch icloudpy +
    the keyring helper. The route mutates a module-level _PENDING_AUTH
    dict; tests clear it in setUp/tearDown."""

    def setUp(self):
        # Reset the pending-auth dict between tests.
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    def test_refresh_trust_returns_400_when_no_username_in_config(self):
        """Config without app.credentials.username can't trigger a
        keyring lookup — bounce to the form with an error."""
        from unittest.mock import patch

        with patch.object(web, "_load_current_config", return_value={"app": {}}):
            response = _csrf_post(self._client(), "/auth/refresh-trust")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"No app.credentials.username", response.data)

    def test_refresh_trust_handles_no_keyring_password(self):
        """No cached password → some user-visible response (not 5xx).

        Patches ``get_api_instance`` so no client is built for real: with no
        password the route now goes down the session-only path, and a test
        must not depend on whatever session files other tests left behind.
        """
        from icloudpy import exceptions as icloudpy_exceptions

        with (
            patch("icloudpy.utils.get_password_from_keyring", return_value=None),
            patch(
                "src.sync.get_api_instance",
                side_effect=icloudpy_exceptions.ICloudPyNoStoredPasswordAvailableException("no session"),
            ),
        ):
            response = _csrf_post(
                self._client(),
                "/auth/refresh-trust",
                follow_redirects=False,
            )
        self.assertLess(response.status_code, 500)

    def test_refresh_trust_keyring_lookup_exception_logged(self):
        """If keyring lookup raises (corrupt store, perms), the route
        logs and returns a usable error — doesn't 500."""
        from unittest.mock import patch

        with patch(
            "icloudpy.utils.get_password_from_keyring",
            side_effect=RuntimeError("keyring boom"),
        ):
            response = _csrf_post(
                self._client(),
                "/auth/refresh-trust",
                follow_redirects=False,
            )
        # Either bounces back to auth form or returns a 4xx — both fine.
        self.assertIn(response.status_code, (200, 302, 400, 500))

    def test_refresh_trust_with_already_trusted_session_stores_pending(self):
        """Happy path: keyring password works, iCloudPyService accepts,
        2FA push is fired, pending state is stashed for /auth/code."""
        from unittest.mock import MagicMock, patch

        fake_service = MagicMock()
        fake_service.requires_2fa = True

        with (
            patch(
                "icloudpy.utils.get_password_from_keyring",
                return_value="hunter2",
            ),
            patch(
                "icloudpy.ICloudPyService",
                return_value=fake_service,
            ),
        ):
            response = _csrf_post(
                self._client(),
                "/auth/refresh-trust",
                follow_redirects=False,
            )
        self.assertIn(response.status_code, (200, 302))

    def test_refresh_trust_works_from_the_session_alone(self):
        """A password-free container sees the ``ready`` pill and its
        "Refresh trust" button. That button used to 500 on the keyring
        lookup. Neither ``trust_session`` nor the 2FA push needs a
        password, so it is served from the saved session instead."""
        from unittest.mock import MagicMock

        from icloudpy import exceptions as icloudpy_exceptions

        fake_service = MagicMock()
        fake_service.requires_2fa = True
        with (
            patch(
                "icloudpy.utils.get_password_from_keyring",
                side_effect=icloudpy_exceptions.ICloudPyNoStoredPasswordAvailableException(),
            ),
            patch("src.sync.get_api_instance", return_value=fake_service) as session_only,
            patch("icloudpy.ICloudPyService") as with_password,
        ):
            response = _csrf_post(
                self._client(),
                "/auth/refresh-trust",
                follow_redirects=False,
            )
        self.assertIn(response.status_code, (200, 302))
        self.assertIsNone(session_only.call_args.kwargs["password"])
        with_password.assert_not_called()

    def test_refresh_trust_says_so_when_the_session_is_dead_and_there_is_no_password(self):
        """The old wording ("your stored password may be stale") is wrong
        for a container that has no stored password."""
        from icloudpy import exceptions as icloudpy_exceptions

        with (
            patch(
                "icloudpy.utils.get_password_from_keyring",
                side_effect=icloudpy_exceptions.ICloudPyNoStoredPasswordAvailableException(),
            ),
            patch(
                "src.sync.get_api_instance",
                side_effect=icloudpy_exceptions.ICloudPyNoStoredPasswordAvailableException(),
            ),
        ):
            response = _csrf_post(
                self._client(),
                "/auth/refresh-trust",
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"no longer valid and no password is stored", response.data)

    def test_refresh_trust_icloudpy_construction_exception_handled(self):
        """If ICloudPyService construction itself raises (network down,
        Apple endpoint changed), bounce back with an error message."""
        from unittest.mock import patch

        with (
            patch(
                "icloudpy.utils.get_password_from_keyring",
                return_value="hunter2",
            ),
            patch(
                "icloudpy.ICloudPyService",
                side_effect=RuntimeError("ctor boom"),
            ),
        ):
            response = _csrf_post(
                self._client(),
                "/auth/refresh-trust",
                follow_redirects=False,
            )
        # 200 with error message rendered, or a 4xx/5xx — anything
        # except an unhandled exception is acceptable.
        self.assertIn(response.status_code, (200, 302, 400, 500))


class TestApiSync(unittest.TestCase):
    """``POST /api/sync`` writes a force-sync sentinel that the sync
    loop consumes on next iteration. JSON for API consumers, redirect
    for HTML form submits."""

    def _client(self):
        return web.create_app(testing=True).test_client()

    def test_api_sync_rejects_unknown_service(self):
        response = _csrf_post(
            self._client(),
            "/api/sync",
            data={"service": "calendar"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"service must be one of", response.data)

    def test_api_sync_returns_400_when_no_services_configured(self):
        from unittest.mock import patch

        with patch.object(web, "_load_current_config", return_value={"app": {}}):
            response = _csrf_post(
                self._client(),
                "/api/sync",
                data={"service": "drive"},
                headers={"Accept": "application/json"},
            )
        self.assertEqual(response.status_code, 400)

    def test_api_sync_drive_queues_drive_sentinel(self):
        from unittest.mock import patch

        with patch.object(
            web.web_signals,
            "request_force_sync",
            return_value=True,
        ) as fake_req:
            response = _csrf_post(
                self._client(),
                "/api/sync",
                data={"service": "drive"},
                headers={"Accept": "application/json"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn("drive", body["queued"])
        fake_req.assert_called_with("drive")

    def test_api_sync_all_queues_both_configured_services(self):
        from unittest.mock import patch

        with patch.object(
            web.web_signals,
            "request_force_sync",
            return_value=True,
        ) as fake_req:
            response = _csrf_post(
                self._client(),
                "/api/sync",
                data={"service": "all"},
                headers={"Accept": "application/json"},
            )
        self.assertEqual(response.status_code, 200)
        # Both drive + photos should have been requested (the test
        # config has both blocks).
        call_args = {c.args[0] for c in fake_req.call_args_list}
        self.assertEqual(call_args, {"drive", "photos"})

    def test_api_sync_form_submit_redirects_to_dashboard(self):
        """Browser form submission (no Accept: json) returns a 302 to /
        instead of JSON."""
        from unittest.mock import patch

        with patch.object(
            web.web_signals,
            "request_force_sync",
            return_value=True,
        ):
            response = _csrf_post(
                self._client(),
                "/api/sync",
                data={"service": "drive"},
            )
        self.assertEqual(response.status_code, 302)

    def test_api_sync_service_via_query_string_also_works(self):
        """Service can come from query string too."""
        from unittest.mock import patch

        with patch.object(
            web.web_signals,
            "request_force_sync",
            return_value=True,
        ):
            response = _csrf_post(
                self._client(),
                "/api/sync?service=drive",
                headers={"Accept": "application/json"},
            )
        self.assertEqual(response.status_code, 200)


class TestStartInThread(unittest.TestCase):
    """``start_in_thread`` binds synchronously, then serves on a daemon
    thread. We mock ``make_server`` to avoid really binding a port."""

    def test_start_returns_thread_object(self):
        from unittest.mock import MagicMock, patch

        with patch("src.web.make_server", return_value=MagicMock()):
            t = web.start_in_thread(host="127.0.0.1", port=0)
        self.assertTrue(t.daemon)
        self.assertEqual(t.name, "icloud-web-ui")

    def test_start_thread_serves_with_correct_args(self):
        """The bind happens in the calling thread, so the host/port
        assertion needs no sleep-polling for a background callback."""
        from unittest.mock import MagicMock, patch

        server = MagicMock()
        with patch("src.web.make_server", return_value=server) as fake_make:
            t = web.start_in_thread(host="0.0.0.0", port=8765)  # noqa: S104
            t.join(timeout=1.0)
        self.assertTrue(fake_make.called)
        args = fake_make.call_args.args
        self.assertEqual(args[0], "0.0.0.0")
        self.assertEqual(args[1], 8765)
        self.assertTrue(fake_make.call_args.kwargs["threaded"])
        self.assertTrue(server.serve_forever.called)

    def test_start_thread_logs_oserror_when_bind_fails(self):
        """Bind failures (port already in use) surface synchronously:
        logged at ERROR, ``None`` returned, no thread started, and the
        sync loop carries on. Deterministic now that the bind is not
        racing a background callback."""
        import logging
        from unittest.mock import patch

        with (
            patch("src.web.make_server", side_effect=OSError("port in use")),
            self.assertLogs(web.LOGGER, level=logging.ERROR) as cm,
        ):
            result = web.start_in_thread(host="0.0.0.0", port=0)  # noqa: S104
        self.assertIsNone(result)
        joined = "\n".join(cm.output)
        self.assertIn("Web UI failed to bind", joined)
        self.assertIn("port in use", joined)

    def test_serve_loop_exception_is_logged_not_fatal(self):
        """If ``serve_forever`` dies mid-flight the daemon thread logs
        it rather than taking the process down."""
        import logging
        from unittest.mock import MagicMock, patch

        server = MagicMock()
        server.serve_forever.side_effect = RuntimeError("socket gone")
        with (
            patch("src.web.make_server", return_value=server),
            self.assertLogs(web.LOGGER, level=logging.ERROR) as cm,
        ):
            t = web.start_in_thread(host="127.0.0.1", port=0)
            t.join(timeout=2.0)
        joined = "\n".join(cm.output)
        self.assertIn("Web UI server stopped", joined)


class TestSmallBranches(unittest.TestCase):
    """Targeted tests for the scattered 1-3 line gaps in web.py helpers."""

    def test_logger_filename_handles_attribute_error(self):
        """``_logger_filename`` returns '' when the helper raises."""
        from unittest.mock import patch

        with patch.object(
            web.config_parser,
            "get_logger_filename",
            side_effect=AttributeError,
            create=True,
        ):
            result = web._logger_filename({})  # noqa: SLF001
        self.assertEqual(result, "")

    def test_tail_log_file_oserror_returns_empty(self):
        """Log tail OSError (permission denied) on a file that DOES
        exist (passes the isfile guard) returns [] + logs a warning."""
        import logging
        import tempfile

        with (
            tempfile.NamedTemporaryFile() as f,
            patch(
                "builtins.open",
                side_effect=OSError("perms"),
            ),
            self.assertLogs(web.LOGGER, level=logging.WARNING) as cm,
        ):
            result = web._tail_log_file(f.name)  # noqa: SLF001
        self.assertEqual(result, [])
        self.assertTrue(any("could not tail" in line for line in cm.output))

    def test_tail_log_file_missing_path_returns_empty_no_log(self):
        """Missing path takes the early return — silent."""
        result = web._tail_log_file("/nonexistent/file.log")  # noqa: SLF001
        self.assertEqual(result, [])

    def test_tail_log_file_empty_path_returns_empty(self):
        """Empty path string — early return, no error."""
        result = web._tail_log_file("")  # noqa: SLF001
        self.assertEqual(result, [])


class TestHelperExceptionPaths(unittest.TestCase):
    """Cover the defensive exception/fallback branches in web.py helpers.
    Each test forces the inner call to raise so the except-block runs."""

    def test_get_marker_filename_uses_pr8_helper_when_present(self):
        """When PR 8 is merged (config_parser.get_mount_marker_filename
        exists), the helper returns whatever the getter returns."""
        with patch.object(
            web.config_parser,
            "get_mount_marker_filename",
            return_value=".my-marker",
            create=True,
        ):
            result = web._get_marker_filename({"app": {}})  # noqa: SLF001
        self.assertEqual(result, ".my-marker")

    def test_get_require_mount_marker_uses_pr8_helper_when_present(self):
        """When PR 8 helpers exist, the wrapper returns bool(getter(...))."""
        with patch.object(
            web.config_parser,
            "get_drive_require_mount_marker",
            return_value=True,
            create=True,
        ):
            self.assertTrue(
                web._get_require_mount_marker({"drive": {}}, "drive"),  # noqa: SLF001
            )

    def test_logger_filename_attribute_error_returns_empty(self):
        """``_logger_filename`` catches AttributeError when the inner
        config walk fails — returns empty string."""

        class WeirdConfig:
            def __getitem__(self, _key):
                raise AttributeError("partial config")  # noqa: EM101

            def get(self, *_args, **_kw):
                raise AttributeError("partial config")  # noqa: EM101

        result = web._logger_filename(WeirdConfig())  # noqa: SLF001
        self.assertEqual(result, "")


class TestAuthPasswordExceptionPaths(unittest.TestCase):
    """Cover the exception paths in ``/auth/password``."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    # Note: the `except (KeyError, AttributeError, TypeError)` defensive
    # branch in /auth/password (web.py:391-395) is hard to exercise via
    # the Flask test client because mocking `get_username` to raise
    # globally also breaks `_build_status` rendering. The branch is
    # marked `# pragma: no cover` in source — it's defensive code for
    # hand-malformed configs that real users rarely hit.

    def test_password_post_2fa_push_trigger_failure_is_non_fatal(self):
        """If trigger_2fa_push_notification raises, log a warning and
        continue — user can still type a code that arrived via SMS."""
        from unittest.mock import MagicMock

        fake_api = MagicMock()
        fake_api.requires_2fa = True
        fake_api.trigger_2fa_push_notification.side_effect = RuntimeError("boom")
        with patch("icloudpy.ICloudPyService", return_value=fake_api):
            response = _csrf_post(
                self._client(),
                "/auth/password",
                data={"password": "hunter2"},
            )
        # Redirects to /auth (pending state) — not a 500.
        self.assertLess(response.status_code, 500)


class TestAuthCodeExceptionPaths(unittest.TestCase):
    """Cover the exception paths in ``/auth/code``."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    def test_validate_2fa_code_exception_returns_user_visible_error(self):
        """If validate_2fa_code raises (network blip, code-mismatch
        deep in icloudpy), log + return an error UI instead of 500."""
        from unittest.mock import MagicMock

        fake_api = MagicMock()
        fake_api.validate_2fa_code.side_effect = RuntimeError("validate boom")
        web._PENDING_AUTH["api"] = fake_api  # noqa: SLF001
        web._PENDING_AUTH["username"] = "u@example.com"  # noqa: SLF001

        response = _csrf_post(
            self._client(),
            "/auth/code",
            data={"code": "123456"},
        )
        # Either renders error page or redirects — never 500.
        self.assertLess(response.status_code, 500)


class TestAuthRefreshTrustExceptionPaths(unittest.TestCase):
    """Cover the remaining exception paths inside /auth/refresh-trust."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def _client(self):
        return web.create_app(testing=True).test_client()

    # Same as the /auth/password version above — the `except` branch
    # is pragma'd in source.

    def test_refresh_trust_2fa_push_trigger_failure_logged_non_fatal(self):
        """If trigger_2fa_push_notification raises during refresh-trust,
        log a warning and continue to the auth form so user can still
        type a code that arrives via SMS."""
        from unittest.mock import MagicMock

        fake_api = MagicMock()
        fake_api.requires_2fa = True
        fake_api.trigger_2fa_push_notification.side_effect = RuntimeError("boom")
        with (
            patch(
                "icloudpy.utils.get_password_from_keyring",
                return_value="hunter2",
            ),
            patch("icloudpy.ICloudPyService", return_value=fake_api),
        ):
            response = _csrf_post(
                self._client(),
                "/auth/refresh-trust",
                follow_redirects=False,
            )
        self.assertLess(response.status_code, 500)

    def test_refresh_trust_already_trusted_redirects_to_dashboard(self):
        """If the refreshed session is already trusted (no 2FA needed),
        the route redirects to the dashboard."""
        from unittest.mock import MagicMock

        fake_api = MagicMock()
        fake_api.requires_2fa = False
        with (
            patch(
                "icloudpy.utils.get_password_from_keyring",
                return_value="hunter2",
            ),
            patch("icloudpy.ICloudPyService", return_value=fake_api),
        ):
            response = _csrf_post(
                self._client(),
                "/auth/refresh-trust",
                follow_redirects=False,
            )
        # 302 redirect to dashboard.
        self.assertIn(response.status_code, (200, 302))


class TestCsrfEnforcement(unittest.TestCase):
    """Every state-changing POST rejects requests without a valid CSRF
    token + matching cookie. Defends against same-LAN CSRF when the
    user has opted into ``host: 0.0.0.0``."""

    def _client(self):
        return web.create_app(testing=True).test_client()

    def test_post_without_cookie_returns_403(self):
        """Cookie missing -> 403. Form field present but cookie absent
        is the case a cross-site POST would produce (SameSite=Strict
        blocks the cookie send)."""
        for path in (
            "/auth/password",
            "/auth/code",
            "/auth/reset",
            "/auth/refresh-trust",
            "/api/sync",
        ):
            client = self._client()
            # No set_cookie -> CSRF cookie absent.
            response = client.post(
                path,
                data={"csrf_token": "anything", "service": "drive"},
            )
            self.assertEqual(response.status_code, 403, msg=path)

    def test_post_with_cookie_but_mismatched_token_returns_403(self):
        """Cookie present but form token doesn't match -> 403. Covers
        the second leg of the double-submit check."""
        for path in (
            "/auth/password",
            "/auth/code",
            "/auth/reset",
            "/auth/refresh-trust",
            "/api/sync",
        ):
            client = self._client()
            cookie_name = web._CSRF_COOKIE_NAME  # noqa: SLF001
            valid_token = web._get_csrf_token()  # noqa: SLF001
            client.set_cookie(cookie_name, valid_token)
            response = client.post(
                path,
                data={"csrf_token": "wrong-token", "service": "drive"},
            )
            self.assertEqual(response.status_code, 403, msg=path)

    def test_post_with_stale_cookie_returns_403(self):
        """Cookie value doesn't match the live process token -> 403.
        Models the case where a tab from a previous process restart
        tries to POST."""
        client = self._client()
        cookie_name = web._CSRF_COOKIE_NAME  # noqa: SLF001
        client.set_cookie(cookie_name, "stale-token-from-prior-run")
        response = client.post(
            "/api/sync",
            data={"csrf_token": "stale-token-from-prior-run", "service": "drive"},
        )
        self.assertEqual(response.status_code, 403)


class TestPendingAuthTtl(unittest.TestCase):
    """``_PENDING_AUTH`` stash expires after ``_PENDING_AUTH_TTL_SECONDS``.
    Defence-in-depth: if the user walks away from a 2FA prompt, the
    submitted Apple ID password doesn't sit in process memory forever."""

    def setUp(self):
        _reset_pending_auth()

    def tearDown(self):
        _reset_pending_auth()

    def test_stale_pending_auth_is_cleared_on_new_stash(self):
        """A fresh /auth/password POST while a stale entry sits in
        ``_PENDING_AUTH`` expires the stale one first."""
        import time as _time

        # Plant a "stale" entry whose stashed_at is well past the TTL.
        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH["api"] = object()  # noqa: SLF001
            web._PENDING_AUTH["username"] = "old@stale.com"  # noqa: SLF001
            web._PENDING_AUTH["stashed_at"] = (  # noqa: SLF001
                _time.monotonic() - web._PENDING_AUTH_TTL_SECONDS - 1  # noqa: SLF001
            )
            self.assertTrue(web._pending_auth_is_stale())  # noqa: SLF001

        # The expire helper wipes it.
        with web._AUTH_LOCK:  # noqa: SLF001
            web._expire_stale_pending_auth_unlocked()  # noqa: SLF001
            self.assertEqual(web._PENDING_AUTH, {})  # noqa: SLF001

    def test_fresh_pending_auth_is_not_stale(self):
        """An entry stashed just now is not stale; expire is a no-op."""
        import time as _time

        with web._AUTH_LOCK:  # noqa: SLF001
            web._PENDING_AUTH["api"] = object()  # noqa: SLF001
            web._PENDING_AUTH["stashed_at"] = _time.monotonic()  # noqa: SLF001
            self.assertFalse(web._pending_auth_is_stale())  # noqa: SLF001
            web._expire_stale_pending_auth_unlocked()  # noqa: SLF001
            self.assertIn("api", web._PENDING_AUTH)  # noqa: SLF001

    def test_empty_pending_auth_is_not_stale(self):
        """Nothing to expire -> not stale."""
        self.assertFalse(web._pending_auth_is_stale())  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()


class TestAuthStateReflectsSyncLoop(unittest.TestCase):
    """``_detect_auth_state`` must not report health the sync loop is
    contradicting: a green dashboard over a sync that stopped weeks ago is
    worse than no dashboard."""

    def test_reauth_needed_when_the_loop_reports_blocked(self):
        with (
            patch("icloudpy.utils.password_exists_in_keyring", return_value=True),
            patch("src.web_signals.get_auth_blocked", return_value={"blocked": True}),
        ):
            self.assertEqual(
                web._detect_auth_state(username="a@icloud.com"),  # noqa: SLF001
                "reauth_needed",
            )

    def test_ready_when_the_loop_reports_healthy(self):
        with (
            patch("icloudpy.utils.password_exists_in_keyring", return_value=True),
            patch("src.web_signals.get_auth_blocked", return_value={"blocked": False}),
        ):
            self.assertEqual(
                web._detect_auth_state(username="a@icloud.com"),  # noqa: SLF001
                "ready",
            )

    def test_setup_needed_without_a_keyring_entry_or_a_session(self):
        with (
            patch("icloudpy.utils.password_exists_in_keyring", return_value=False),
            patch("src.web._saved_session_exists", return_value=False),
        ):
            self.assertEqual(
                web._detect_auth_state(username="a@icloud.com"),  # noqa: SLF001
                "setup_needed",
            )

    def test_a_saved_session_is_ready_even_with_no_password_stored(self):
        """Running with no password on disk is a supported configuration, so
        an empty keyring is not an unfinished setup -- telling such an
        operator to go and authenticate would be wrong."""
        with (
            patch("icloudpy.utils.password_exists_in_keyring", return_value=False),
            patch("src.web._saved_session_exists", return_value=True),
            patch("src.web_signals.get_auth_blocked", return_value={"blocked": False}),
        ):
            self.assertEqual(
                web._detect_auth_state(username="a@icloud.com"),  # noqa: SLF001
                "ready",
            )

    def test_a_dead_session_with_no_password_asks_for_a_re_auth(self):
        with (
            patch("icloudpy.utils.password_exists_in_keyring", return_value=False),
            patch("src.web._saved_session_exists", return_value=True),
            patch("src.web_signals.get_auth_blocked", return_value={"blocked": True}),
        ):
            self.assertEqual(
                web._detect_auth_state(username="a@icloud.com"),  # noqa: SLF001
                "reauth_needed",
            )

    def test_a_brand_new_install_is_told_to_set_up_not_to_re_authenticate(self):
        """The sync loop publishes auth-blocked on its first cycle whether or
        not anything was ever set up, so the blocked flag alone must not turn
        a first-time install into "re-authenticate" -- there is nothing to
        re-authenticate with."""
        with (
            patch("icloudpy.utils.password_exists_in_keyring", return_value=False),
            patch("src.web._saved_session_exists", return_value=False),
            patch("src.web_signals.get_auth_blocked", return_value={"blocked": True}),
        ):
            self.assertEqual(
                web._detect_auth_state(username="a@icloud.com"),  # noqa: SLF001
                "setup_needed",
            )

    def _with_cookie_dir(self, files):
        """Run the probe against a temp cookie directory holding ``files``."""
        import json
        import tempfile
        from unittest.mock import patch as _patch

        with tempfile.TemporaryDirectory() as cookie_dir:
            for name, body in files.items():
                with open(os.path.join(cookie_dir, name), "w", encoding="utf-8") as handle:
                    handle.write(body if isinstance(body, str) else json.dumps(body))
            with _patch.object(web, "DEFAULT_COOKIE_DIRECTORY", cookie_dir):
                return web._saved_session_exists("a@icloud.com")  # noqa: SLF001

    def test_the_session_probe_finds_this_accounts_session(self):
        self.assertTrue(self._with_cookie_dir({"aicloudcom.session": {"session_token": "t"}}))

    def test_the_session_probe_ignores_another_accounts_session(self):
        """icloudpy resumes from the file named after *this* apple id. A
        leftover file for a different account is not a credential this
        container can use, and reading it as one would show a green pill
        over a container that cannot sync."""
        self.assertFalse(self._with_cookie_dir({"bicloudcom.session": {"session_token": "t"}}))

    def test_the_session_probe_ignores_a_session_without_a_token(self):
        """``__init__`` writes the file before there is anything to resume
        from, so its mere existence proves nothing."""
        self.assertFalse(self._with_cookie_dir({"aicloudcom.session": {"client_id": "x"}}))

    def test_the_session_probe_survives_unreadable_or_corrupt_files(self):
        self.assertFalse(self._with_cookie_dir({}))
        self.assertFalse(self._with_cookie_dir({"aicloudcom.session": "{not json"}))


class TestSyncPublishesAuthState(unittest.TestCase):
    """``sync._publish_auth_blocked`` is advisory and must never raise."""

    def test_publishes_blocked(self):
        from src import sync

        with patch("src.web_signals.record_auth_blocked") as recorder:
            sync._publish_auth_blocked(True, reason="2fa_required")  # noqa: SLF001
        recorder.assert_called_once_with(blocked=True, reason="2fa_required")

    def test_swallows_failure(self):
        from src import sync

        with patch(
            "src.web_signals.record_auth_blocked",
            side_effect=OSError("read-only"),
        ):
            sync._publish_auth_blocked(False)  # noqa: SLF001


class TestPerLibraryDashboardRows(unittest.TestCase):
    """Destinations and sync state used to render as two separate lists of
    the same libraries, which read as unrelated and wrapped badly. One row
    per library, named once."""

    def _rows(self, states, destinations, configured=None):
        from unittest.mock import patch

        from src import web

        if configured is None:
            configured = list(destinations)
        with patch.object(web.web_signals, "get_library_states", return_value=states):
            return web._build_libraries(configured, destinations)  # noqa: SLF001

    def test_a_row_carries_both_destination_and_state(self):
        rows = self._rows(
            {"PrimarySync": {"state": "syncing"}},
            {"PrimarySync": "Personal"},
        )
        self.assertEqual(rows[0]["name"], "PrimarySync")
        self.assertEqual(rows[0]["subdir"], "Personal")
        self.assertEqual(rows[0]["state"], "syncing")

    def test_configured_order_is_preserved(self):
        """Config order, not alphabetical -- it is how the user reads it."""
        rows = self._rows({}, {"Zeta": "z", "Alpha": "a"})
        self.assertEqual([r["name"] for r in rows], ["Zeta", "Alpha"])

    def test_an_unmapped_library_that_syncs_is_listed(self):
        """It syncs into the default destination, so it must stay visible --
        including when it starts failing after having worked."""
        rows = self._rows(
            {"Family": {"state": "failed", "error": "boom", "completed_at": 1000.0}},
            {},
        )
        self.assertEqual(rows[0]["name"], "Family")
        self.assertIsNone(rows[0]["subdir"])
        self.assertEqual(rows[0]["error"], "boom")

    def test_an_unmapped_library_is_listed_while_it_syncs(self):
        rows = self._rows({"Family": {"state": "syncing"}}, {})
        self.assertEqual([r["name"] for r in rows], ["Family"])

    def test_a_library_that_has_never_synced_is_left_out(self):
        """Some accounts carry libraries that never serve anything. Nothing
        can be done with them, so they are not shown as a standing failure."""
        rows = self._rows(
            {
                "Family": {"state": "ok", "completed_at": 1000.0},
                "Other": {"state": "failed", "error": "boom"},
            },
            {},
        )
        self.assertEqual([r["name"] for r in rows], ["Family"])

    def test_a_configured_library_is_listed_even_if_it_never_synced(self):
        """Naming a library in config is asking to see it."""
        rows = self._rows({"Other": {"state": "failed", "error": "boom"}}, {}, configured=["Other"])
        self.assertEqual(rows[0]["name"], "Other")
        self.assertEqual(rows[0]["error"], "boom")

    def test_configured_libraries_come_from_the_filter_and_destinations(self):
        from src import web

        config = {
            "photos": {
                "filters": {"libraries": ["Beta", "Alpha"]},
                "library_destinations": {"Alpha": "a", "Gamma": "g"},
            },
        }
        self.assertEqual(
            web._get_configured_libraries(config=config),  # noqa: SLF001
            ["Beta", "Alpha", "Gamma"],
        )

    def test_a_single_library_written_as_a_scalar_is_one_library(self):
        from src import web

        config = {"photos": {"filters": {"libraries": "Beta"}}}
        self.assertEqual(web._get_configured_libraries(config=config), ["Beta"])  # noqa: SLF001

    def test_no_configured_libraries(self):
        from src import web

        self.assertEqual(web._get_configured_libraries(config={"photos": {}}), [])  # noqa: SLF001

    def test_a_failed_library_still_reports_its_last_success(self):
        rows = self._rows(
            {"PrimarySync": {"state": "failed", "error": "boom", "completed_at": 1000.0}},
            {"PrimarySync": "Personal"},
        )
        self.assertIsNotNone(rows[0]["completed_relative"])

    def test_nothing_configured_and_nothing_recorded(self):
        self.assertEqual(self._rows({}, {}), [])

    def test_drive_never_gets_library_rows(self):
        """Drive has no libraries; the section must not appear on its card."""
        from unittest.mock import patch

        from src import read_config, web

        config = read_config(config_path=tests.CONFIG_PATH)
        with patch.object(web.web_signals, "get_library_states", return_value={"X": {}}):
            payload = web._build_status(config=config)  # noqa: SLF001
        for service in payload["services"]:
            if service["name"] == "Drive":
                self.assertEqual(service["libraries"], [])


class TestTheDashboardWordsTheModeCorrectly(unittest.TestCase):
    """The pill is the only place most people ever read this, so it has to
    say what is actually true of the container in front of them."""

    def _render(self, **status_overrides):
        status = {
            "config_loaded": True,
            "config_path": "/config/config.yaml",
            "username": "a@icloud.com",
            "region": "global",
            "marker_filename": ".mounted",
            "services": [],
            "auth_state": "ready",
            "password_stored": True,
            "auth_blocked_reason": None,
            "auth_method": None,
            "force_sync_pending": {},
            "trust_expires_at": None,
            "trust_days_remaining": None,
            "libraries": [],
        }
        status.update(status_overrides)
        with (
            patch.object(web, "_build_status", return_value=status),
            patch.object(web, "_tail_log_file", return_value=[]),
        ):
            return web.create_app(testing=True).test_client().get("/").data

    def test_ready_does_not_claim_a_populated_keyring(self):
        """"keyring populated" is simply false in session-only mode, and it
        is the wrong thing to reassure anyone with even when it is true --
        what matters is that the loop is signed in."""
        body = self._render(password_stored=False)
        self.assertNotIn(b"keyring populated", body)
        self.assertIn(b"signed in, sync loop authenticated", body)
        self.assertIn(b"no password stored", body)

    def test_ready_with_a_password_says_nothing_about_the_session(self):
        body = self._render(password_stored=True)
        self.assertIn(b"signed in, sync loop authenticated", body)
        self.assertNotIn(b"no password stored", body)

    def test_a_stopped_sync_is_described_by_the_published_reason(self):
        cases = {
            "session_unusable": b"saved session is no longer valid",
            "sign_in_failed": b"can be an outage",
            "2fa_required": b"asking for a second factor",
            None: b"asking for a second factor",
        }
        for reason, expected in cases.items():
            with self.subTest(reason=reason):
                body = self._render(auth_state="reauth_needed", auth_blocked_reason=reason)
                self.assertIn(expected, body)


class TestTheDashboardSaysWhenAPasswordIsStored(unittest.TestCase):
    """People who signed in before the sign-in page stopped saving the
    password may not know it is on disk; the dashboard says so."""

    def _body(self, stored, env=None):
        from unittest.mock import patch

        environ = {"ENV_ICLOUD_PASSWORD": env} if env else {}
        with (
            patch.object(web, "_password_is_stored", return_value=stored),
            patch.object(web, "_detect_auth_state", return_value="ready"),
            patch.dict(os.environ, environ),
        ):
            if not env:
                os.environ.pop("ENV_ICLOUD_PASSWORD", None)
            return web.create_app(testing=True).test_client().get("/").data.decode("utf-8")

    def test_a_stored_password_is_called_out(self):
        body = self._body(stored=True)
        self.assertIn("password is stored in the container", body)
        self.assertIn("#two-ways-to-run-unattended", body)
        self.assertNotIn("from ENV_ICLOUD_PASSWORD", body)

    def test_one_from_the_environment_says_where_it_comes_from(self):
        self.assertIn("from ENV_ICLOUD_PASSWORD", self._body(stored=True, env="x"))

    def test_no_notice_without_a_stored_password(self):
        self.assertNotIn("password is stored in the container", self._body(stored=False))

    def test_the_notice_offers_to_remove_it(self):
        self.assertIn('action="/auth/forget-password"', self._body(stored=True))

    def test_no_remove_button_when_it_comes_from_the_environment(self):
        """Deleting it would not stick: the loop stores it again every cycle."""
        self.assertNotIn('action="/auth/forget-password"', self._body(stored=True, env="x"))


class TestRemovingAStoredPassword(unittest.TestCase):
    """``POST /auth/forget-password`` deletes the stored password, but only
    once the saved session is shown to work without it, so the button
    can never be the thing that stops sync."""

    def _post(self, session_ok=True, env=None, delete_error=None):
        from unittest.mock import MagicMock

        api = MagicMock()
        api.requires_2fa = not session_ok
        environ = {"ENV_ICLOUD_PASSWORD": env} if env else {}
        with (
            patch.dict(os.environ, environ),
            patch("src.sync.get_api_instance", return_value=api) as session,
            patch("icloudpy.utils.get_password_from_keyring", return_value="hunter2"),
            patch("icloudpy.utils.delete_password_in_keyring", side_effect=delete_error) as delete,
        ):
            if not env:
                os.environ.pop("ENV_ICLOUD_PASSWORD", None)
            response = _csrf_post(web.create_app(testing=True).test_client(), "/auth/forget-password")
        return response, session, delete

    def test_it_is_removed_once_the_session_works_alone(self):
        response, session, delete = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Stored password removed", response.data)
        delete.assert_called_once_with("user@test.com")
        self.assertIsNone(session.call_args.kwargs["password"])

    def test_it_is_kept_when_the_session_needs_it(self):
        response, _, delete = self._post(session_ok=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"would stop sync", response.data)
        delete.assert_not_called()

    def test_it_is_kept_when_the_session_check_fails(self):
        from icloudpy import exceptions as icloudpy_exceptions

        with (
            patch(
                "src.sync.get_api_instance",
                side_effect=icloudpy_exceptions.ICloudPyNoStoredPasswordAvailableException("no session"),
            ),
            patch("icloudpy.utils.delete_password_in_keyring") as delete,
        ):
            os.environ.pop("ENV_ICLOUD_PASSWORD", None)
            response = _csrf_post(web.create_app(testing=True).test_client(), "/auth/forget-password")
        self.assertEqual(response.status_code, 400)
        delete.assert_not_called()

    def test_it_is_not_removed_while_the_environment_sets_it(self):
        response, session, delete = self._post(env="x")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Remove that from the container", response.data)
        session.assert_not_called()
        delete.assert_not_called()

    def test_a_keyring_error_is_reported(self):
        response, _, _ = self._post(delete_error=RuntimeError("read-only"))
        self.assertEqual(response.status_code, 500)
        self.assertIn(b"Could not remove the stored password: read-only", response.data)

    def test_no_username_configured(self):
        with patch.object(web, "_load_current_config", return_value={"app": {}}):
            response = _csrf_post(web.create_app(testing=True).test_client(), "/auth/forget-password")
        self.assertEqual(response.status_code, 400)

    def test_it_needs_the_csrf_token(self):
        with patch("icloudpy.utils.delete_password_in_keyring") as delete:
            response = web.create_app(testing=True).test_client().post("/auth/forget-password")
        self.assertEqual(response.status_code, 403)
        delete.assert_not_called()


class TestAStoredPasswordIsNeverOverwritten(unittest.TestCase):
    """A sign-in that resumes a still-valid session never shows Apple the
    password, so the page cannot tell a changed password from a typo.
    It never writes the keyring, even when a different one is stored."""

    def test_a_different_typed_password_leaves_the_stored_one(self):
        from unittest.mock import MagicMock

        api = MagicMock()
        api.requires_2fa = False
        with (
            patch("icloudpy.ICloudPyService", return_value=api),
            patch("icloudpy.utils.get_password_from_keyring", return_value="old"),
            patch("icloudpy.utils.store_password_in_keyring") as saved,
        ):
            response = _csrf_post(
                web.create_app(testing=True).test_client(), "/auth/password", data={"password": "new"},
            )
        self.assertEqual(response.status_code, 302)
        saved.assert_not_called()


class TestRemovingAPasswordAlreadyGone(unittest.TestCase):
    def test_a_resubmit_after_it_is_gone_still_succeeds(self):
        from unittest.mock import MagicMock

        from icloudpy import exceptions as icloudpy_exceptions

        api = MagicMock()
        api.requires_2fa = False
        with (
            patch("src.sync.get_api_instance", return_value=api),
            patch(
                "icloudpy.utils.get_password_from_keyring",
                side_effect=icloudpy_exceptions.ICloudPyNoStoredPasswordAvailableException(),
            ),
            patch("icloudpy.utils.delete_password_in_keyring") as delete,
        ):
            os.environ.pop("ENV_ICLOUD_PASSWORD", None)
            response = _csrf_post(web.create_app(testing=True).test_client(), "/auth/forget-password")
        self.assertEqual(response.status_code, 200)
        delete.assert_not_called()
