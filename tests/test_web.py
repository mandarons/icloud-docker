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
