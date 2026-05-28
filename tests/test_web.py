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
