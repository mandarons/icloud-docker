"""Tests for the trust-expiry notification feature.

Covers the new surface added on top of PR #464 (web UI):
  - ``config_parser.get_web_ui_public_url`` / ``get_trust_expiry_warn_days``
  - ``notify._create_trust_expiring_message`` + ``send_trust_expiring``
  - ``notify._create_2fa_message`` dashboard_url branch
  - ``sync._read_trust_cookie_expiry`` / ``_resolve_dashboard_url`` /
    ``_maybe_warn_trust_expiring``
  - ``web._build_status`` trust_* fields
  - ``web_signals.record_trust_state`` / ``get_trust_state``
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import datetime
import unittest
from unittest.mock import MagicMock, patch

import tests  # noqa: F401  - sets ENV_CONFIG_FILE_PATH


class TestGetWebUiPublicUrl(unittest.TestCase):
    """app.web_ui.public_url reader."""

    def test_returns_none_when_unset(self):
        from src import config_parser

        self.assertIsNone(config_parser.get_web_ui_public_url(config={}))
        self.assertIsNone(
            config_parser.get_web_ui_public_url(config={"app": {"web_ui": {}}}),
        )

    def test_returns_value_when_set(self):
        from src import config_parser

        cfg = {"app": {"web_ui": {"public_url": "https://icloud.example.com"}}}
        self.assertEqual(
            config_parser.get_web_ui_public_url(config=cfg),
            "https://icloud.example.com",
        )

    def test_strips_trailing_slash(self):
        from src import config_parser

        cfg = {"app": {"web_ui": {"public_url": "https://icloud.example.com/"}}}
        self.assertEqual(
            config_parser.get_web_ui_public_url(config=cfg),
            "https://icloud.example.com",
        )


class TestGetTrustExpiryWarnDays(unittest.TestCase):
    """app.trust_expiry_warn_days reader. Default 7."""

    def test_default(self):
        from src import config_parser

        self.assertEqual(config_parser.get_trust_expiry_warn_days(config={}), 7)

    def test_override(self):
        from src import config_parser

        cfg = {"app": {"trust_expiry_warn_days": 14}}
        self.assertEqual(config_parser.get_trust_expiry_warn_days(config=cfg), 14)


class TestCreate2faMessageWithUrl(unittest.TestCase):
    """_create_2fa_message URL branch."""

    def test_url_message_uses_dashboard_url(self):
        from src.notify import _create_2fa_message  # noqa: SLF001

        msg, subj = _create_2fa_message(
            "user@me.com",
            region="global",
            dashboard_url="https://icloud.example.com",
        )
        self.assertIn("https://icloud.example.com/auth", msg)
        # New "icloud-docker:" prefix legitimately contains "docker" --
        # what we actually want to assert is that the legacy "docker exec"
        # instruction is NOT in the URL branch.
        self.assertNotIn("docker exec", msg)
        self.assertIn("icloud-docker:", msg)
        self.assertIn("user@me.com", subj)

    def test_no_url_falls_back(self):
        from src.notify import _create_2fa_message  # noqa: SLF001

        msg, _ = _create_2fa_message("user@me.com", region="global", dashboard_url=None)
        self.assertIn("docker exec", msg)
        self.assertNotIn("https://", msg)


class TestCreateTrustExpiringMessage(unittest.TestCase):
    """_create_trust_expiring_message body shape."""

    def test_url_branch_includes_url_and_horizon(self):
        from src.notify import _create_trust_expiring_message  # noqa: SLF001

        msg, subj = _create_trust_expiring_message(
            "user@me.com",
            days_remaining=5,
            dashboard_url="https://icloud.example.com",
        )
        self.assertIn("https://icloud.example.com", msg)
        self.assertIn("in 5 days", msg)
        # Username dropped from body for terseness; lives in subject for email.
        self.assertNotIn("user@me.com", msg)
        self.assertIn("user@me.com", subj)
        self.assertIn("in 5 days", subj)

    def test_no_url_branch_falls_back(self):
        from src.notify import _create_trust_expiring_message  # noqa: SLF001

        msg, _ = _create_trust_expiring_message(
            "user@me.com",
            days_remaining=3,
            dashboard_url=None,
        )
        self.assertIn("container", msg)
        self.assertNotIn("https://", msg)

    def test_singular_day(self):
        from src.notify import _create_trust_expiring_message  # noqa: SLF001

        _, subj = _create_trust_expiring_message("u@e.com", days_remaining=1)
        self.assertIn("in 1 day", subj)
        self.assertNotIn("in 1 days", subj)

    def test_today_when_expired(self):
        from src.notify import _create_trust_expiring_message  # noqa: SLF001

        _, subj = _create_trust_expiring_message("u@e.com", days_remaining=0)
        self.assertIn("today", subj)
        _, subj_neg = _create_trust_expiring_message("u@e.com", days_remaining=-1)
        self.assertIn("today", subj_neg)


class TestSendTrustExpiring(unittest.TestCase):
    """send_trust_expiring fans the message to all configured channels."""

    def _config(self):
        return {"app": {"telegram": {"bot_token": "x", "chat_id": "y"}}}

    def test_returns_sent_timestamp_when_any_channel_succeeds(self):
        from src import notify

        ts = datetime.datetime.now()
        with (
            patch.object(notify, "notify_telegram", return_value=ts),
            patch.object(notify, "notify_discord", return_value=None),
            patch.object(notify, "notify_pushover", return_value=None),
            patch.object(notify, "notify_email", return_value=None),
        ):
            result = notify.send_trust_expiring(
                config=self._config(),
                username="u@e.com",
                days_remaining=5,
            )
        self.assertEqual(result, ts)

    def test_returns_none_when_all_fail(self):
        from src import notify

        with (
            patch.object(notify, "notify_telegram", return_value=None),
            patch.object(notify, "notify_discord", return_value=None),
            patch.object(notify, "notify_pushover", return_value=None),
            patch.object(notify, "notify_email", return_value=None),
        ):
            result = notify.send_trust_expiring(
                config=self._config(),
                username="u@e.com",
                days_remaining=5,
            )
        self.assertIsNone(result)

    def test_threads_dashboard_url_into_message(self):
        from src import notify

        captured = {}

        def _capture(config, message, last_send=None, dry_run=False):
            captured["msg"] = message
            return None

        with (
            patch.object(notify, "notify_telegram", side_effect=_capture),
            patch.object(notify, "notify_discord", return_value=None),
            patch.object(notify, "notify_pushover", return_value=None),
            patch.object(notify, "notify_email", return_value=None),
        ):
            notify.send_trust_expiring(
                config=self._config(),
                username="u@e.com",
                days_remaining=5,
                dashboard_url="https://icloud.example.com",
            )
        self.assertIn("https://icloud.example.com", captured["msg"])


def _fake_cookie(name, expires):
    cookie = MagicMock()
    cookie.name = name
    cookie.expires = expires
    return cookie


class TestReadTrustCookieExpiry(unittest.TestCase):
    """sync._read_trust_cookie_expiry."""

    def test_returns_expiry_when_cookie_present(self):
        from src import sync

        expires_unix = 1893456000
        api = MagicMock()
        api.session.cookies = [
            _fake_cookie("X-APPLE-WEBAUTH-LOGIN", 0),
            _fake_cookie("X-APPLE-WEBAUTH-HSA-TRUST", expires_unix),
            _fake_cookie("X-APPLE-WEBAUTH-PCS-Photos", 1893456000),
        ]
        result = sync._read_trust_cookie_expiry(api)  # noqa: SLF001
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.year, 2030)
        self.assertIsNotNone(result.tzinfo)

    def test_returns_none_when_cookie_absent(self):
        from src import sync

        api = MagicMock()
        api.session.cookies = [_fake_cookie("X-APPLE-WEBAUTH-LOGIN", 0)]
        self.assertIsNone(sync._read_trust_cookie_expiry(api))  # noqa: SLF001

    def test_returns_none_when_cookie_has_no_expires(self):
        from src import sync

        api = MagicMock()
        api.session.cookies = [_fake_cookie("X-APPLE-WEBAUTH-HSA-TRUST", None)]
        self.assertIsNone(sync._read_trust_cookie_expiry(api))  # noqa: SLF001

    def test_returns_none_when_session_missing(self):
        from src import sync

        class _NoSession:
            pass

        self.assertIsNone(sync._read_trust_cookie_expiry(_NoSession()))  # noqa: SLF001


class TestResolveDashboardUrl(unittest.TestCase):
    """sync._resolve_dashboard_url."""

    def test_returns_none_when_web_ui_disabled(self):
        from src import sync

        self.assertIsNone(sync._resolve_dashboard_url(config={}))  # noqa: SLF001

    def test_returns_public_url_when_set(self):
        from src import sync

        cfg = {
            "app": {
                "web_ui": {
                    "enabled": True,
                    "public_url": "https://icloud.example.com",
                },
            },
        }
        self.assertEqual(
            sync._resolve_dashboard_url(config=cfg),  # noqa: SLF001
            "https://icloud.example.com",
        )

    def test_falls_back_to_host_port_when_public_url_unset(self):
        from src import sync

        cfg = {"app": {"web_ui": {"enabled": True, "port": 9090}}}
        self.assertEqual(
            sync._resolve_dashboard_url(config=cfg),  # noqa: SLF001
            "http://127.0.0.1:9090",
        )


class TestMaybeWarnTrustExpiring(unittest.TestCase):
    """sync._maybe_warn_trust_expiring orchestrator."""

    def setUp(self):
        from src import web_signals

        web_signals.record_trust_state(
            expires_at_iso=None,
            warned_for_expires_at="",
        )

    def _api_with_trust_cookie(self, expires_unix):
        api = MagicMock()
        api.session.cookies = [
            _fake_cookie("X-APPLE-WEBAUTH-HSA-TRUST", expires_unix),
        ]
        return api

    def _far_future_expires(self):
        return int((datetime.datetime.now() + datetime.timedelta(days=60)).timestamp())

    def _near_future_expires(self):
        return int((datetime.datetime.now() + datetime.timedelta(days=3)).timestamp())

    def test_no_warning_when_days_above_threshold(self):
        from src import notify, sync

        api = self._api_with_trust_cookie(self._far_future_expires())
        with patch.object(notify, "send_trust_expiring") as send:
            sync._maybe_warn_trust_expiring({}, api, "u@e.com")  # noqa: SLF001
        send.assert_not_called()

    def test_warning_fires_when_days_below_threshold(self):
        from src import notify, sync

        api = self._api_with_trust_cookie(self._near_future_expires())
        with patch.object(notify, "send_trust_expiring") as send:
            sync._maybe_warn_trust_expiring({}, api, "u@e.com")  # noqa: SLF001
        send.assert_called_once()

    def test_debounce_skips_when_already_warned(self):
        from src import notify, sync

        api = self._api_with_trust_cookie(self._near_future_expires())
        with patch.object(notify, "send_trust_expiring") as send:
            sync._maybe_warn_trust_expiring({}, api, "u@e.com")  # noqa: SLF001
            sync._maybe_warn_trust_expiring({}, api, "u@e.com")  # noqa: SLF001
            sync._maybe_warn_trust_expiring({}, api, "u@e.com")  # noqa: SLF001
        send.assert_called_once()

    def test_cookie_refresh_rearms_warning(self):
        from src import notify, sync

        first = self._near_future_expires()
        with patch.object(notify, "send_trust_expiring") as send:
            sync._maybe_warn_trust_expiring(  # noqa: SLF001
                {},
                self._api_with_trust_cookie(first),
                "u@e.com",
            )
            sync._maybe_warn_trust_expiring(  # noqa: SLF001
                {},
                self._api_with_trust_cookie(first),
                "u@e.com",
            )
        self.assertEqual(send.call_count, 1)

        second = first + 86400
        with patch.object(notify, "send_trust_expiring") as send2:
            sync._maybe_warn_trust_expiring(  # noqa: SLF001
                {},
                self._api_with_trust_cookie(second),
                "u@e.com",
            )
        send2.assert_called_once()

    def test_no_cookie_records_none_no_warning(self):
        from src import notify, sync, web_signals

        api = MagicMock()
        api.session.cookies = []
        with patch.object(notify, "send_trust_expiring") as send:
            sync._maybe_warn_trust_expiring({}, api, "u@e.com")  # noqa: SLF001
        send.assert_not_called()
        self.assertIsNone(web_signals.get_trust_state().get("expires_at"))


class TestBuildStatusTrustFields(unittest.TestCase):
    """_build_status surfaces trust_expires_at + trust_days_remaining."""

    def setUp(self):
        from src import web_signals

        web_signals.record_trust_state(
            expires_at_iso=None,
            warned_for_expires_at="",
        )

    def _client(self):
        from src import web

        return web.create_app(testing=True).test_client()

    def test_status_includes_trust_fields_when_recorded(self):
        from src import web_signals

        expires = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(
            days=42,
        )
        web_signals.record_trust_state(expires_at_iso=expires.isoformat())

        payload = self._client().get("/api/status").get_json()
        self.assertEqual(payload["trust_expires_at"], expires.isoformat())
        self.assertIn(payload["trust_days_remaining"], (41, 42))

    def test_status_trust_fields_null_when_no_state(self):
        payload = self._client().get("/api/status").get_json()
        self.assertIsNone(payload["trust_expires_at"])
        self.assertIsNone(payload["trust_days_remaining"])


class TestWebSignalsTrustState(unittest.TestCase):
    """record_trust_state / get_trust_state round trip."""

    def setUp(self):
        from src import web_signals

        web_signals.record_trust_state(
            expires_at_iso=None,
            warned_for_expires_at="",
        )

    def test_round_trip(self):
        from src import web_signals

        iso = "2030-01-01T00:00:00+00:00"
        web_signals.record_trust_state(expires_at_iso=iso, warned_for_expires_at=iso)
        state = web_signals.get_trust_state()
        self.assertEqual(state["expires_at"], iso)
        self.assertEqual(state["warned_for_expires_at"], iso)
        self.assertIn("last_updated", state)

    def test_record_without_warned_keeps_prior(self):
        from src import web_signals

        web_signals.record_trust_state(
            expires_at_iso="2030-01-01T00:00:00+00:00",
            warned_for_expires_at="2030-01-01T00:00:00+00:00",
        )
        web_signals.record_trust_state(expires_at_iso="2030-01-02T00:00:00+00:00")
        state = web_signals.get_trust_state()
        self.assertEqual(state["expires_at"], "2030-01-02T00:00:00+00:00")
        self.assertEqual(state["warned_for_expires_at"], "2030-01-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
