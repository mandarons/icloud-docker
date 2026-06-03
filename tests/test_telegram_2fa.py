"""Tests for headless 2FA-over-Telegram: poller, config getters, notify routing, wait loop."""

import unittest
from unittest.mock import MagicMock, patch

import requests

from src import config_parser, notify, sync
from src.sync import SyncState


class _Resp:
    """Minimal stand-in for a ``requests`` Response."""

    def __init__(self, status_code=200, payload=None, text="", raise_json=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"result": []}
        self.text = text
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            msg = "bad json"
            raise ValueError(msg)
        return self._payload


class TestPollTelegramForText(unittest.TestCase):
    """notify.poll_telegram_for_text -- getUpdates polling."""

    @patch("src.notify.requests.post", side_effect=requests.RequestException("boom"))
    def test_network_error_returns_offset_unchanged(self, _post):
        """Network failure is swallowed; offset preserved."""
        self.assertEqual(notify.poll_telegram_for_text("t", "c", offset=5), (None, 5))

    @patch("src.notify.requests.post", return_value=_Resp(status_code=500, text="err"))
    def test_non_200_returns_offset_unchanged(self, _post):
        """A non-200 response is logged and swallowed."""
        self.assertEqual(notify.poll_telegram_for_text("t", "c", offset=5), (None, 5))

    @patch("src.notify.requests.post", return_value=_Resp(raise_json=True))
    def test_malformed_json_returns_offset_unchanged(self, _post):
        """Malformed JSON is logged and swallowed."""
        self.assertEqual(notify.poll_telegram_for_text("t", "c", offset=5), (None, 5))

    @patch("src.notify.requests.post", return_value=_Resp(payload={"result": []}))
    def test_no_updates(self, _post):
        """Empty result set returns no text."""
        self.assertEqual(notify.poll_telegram_for_text("t", "c", offset=5), (None, 5))

    @patch("src.notify.requests.post")
    def test_foreign_chat_skipped_then_our_text(self, post):
        """Foreign-chat updates advance the offset; our text is returned."""
        post.return_value = _Resp(
            payload={
                "result": [
                    {
                        "update_id": 7,
                        "message": {"chat": {"id": "other"}, "text": "nope"},
                    },
                    {
                        "update_id": 8,
                        "message": {"chat": {"id": "c"}, "text": "  hello  "},
                    },
                ],
            },
        )
        self.assertEqual(notify.poll_telegram_for_text("t", "c", offset=0), ("hello", 8))

    @patch("src.notify.requests.post")
    def test_our_text_without_int_update_id_falls_back_to_offset(self, post):
        """A text message lacking an int update_id returns the running offset."""
        post.return_value = _Resp(
            payload={"result": [{"message": {"chat": {"id": "c"}, "text": "hi"}}]},
        )
        self.assertEqual(notify.poll_telegram_for_text("t", "c", offset=4), ("hi", 4))

    @patch("src.notify.requests.post")
    def test_our_nontext_message_advances_offset(self, post):
        """A non-text message from our chat advances the offset and yields no text."""
        post.return_value = _Resp(
            payload={"result": [{"update_id": 9, "message": {"chat": {"id": "c"}, "text": ""}}]},
        )
        self.assertEqual(notify.poll_telegram_for_text("t", "c", offset=2), (None, 9))

    @patch("src.notify.requests.post")
    def test_foreign_chat_without_int_update_id(self, post):
        """A foreign-chat update with no int update_id is skipped without advancing."""
        post.return_value = _Resp(
            payload={"result": [{"update_id": None, "message": {"chat": {"id": "other"}}}]},
        )
        self.assertEqual(notify.poll_telegram_for_text("t", "c", offset=3), (None, 3))


class TestTelegramConfigGetters(unittest.TestCase):
    """config_parser telegram listen / auth_keyword getters."""

    def test_listen_enabled_true(self):
        config = {"app": {"telegram": {"listen": True}}}
        self.assertTrue(config_parser.get_telegram_listen_enabled(config=config))

    def test_listen_disabled_by_default(self):
        config = {"app": {"telegram": {}}}
        self.assertFalse(config_parser.get_telegram_listen_enabled(config=config))

    def test_auth_keyword_default(self):
        config = {"app": {"telegram": {}}}
        self.assertEqual(config_parser.get_telegram_auth_keyword(config=config), "auth")

    def test_auth_keyword_custom_is_normalised(self):
        config = {"app": {"telegram": {"auth_keyword": "  Auth-Photos  "}}}
        self.assertEqual(config_parser.get_telegram_auth_keyword(config=config), "auth-photos")


class TestNotifySendListenAware(unittest.TestCase):
    """notify.send routes the reply prompt to Telegram only when listen is on."""

    def test_reply_prompt_contains_keyword(self):
        config = {"app": {"telegram": {"auth_keyword": "go-photos"}}}
        prompt = notify._create_telegram_reply_prompt(config)  # noqa: SLF001
        self.assertIn("go-photos", prompt)
        self.assertIn("Reply", prompt)

    @patch("src.notify.notify_email", return_value=None)
    @patch("src.notify.notify_pushover", return_value=None)
    @patch("src.notify.notify_discord", return_value=None)
    @patch("src.notify.notify_telegram", return_value=None)
    def test_listen_on_sends_prompt_to_telegram_standard_to_others(self, tg, discord, _push, _email):
        """Listen on: Telegram gets the reply prompt; other channels get the standard alert."""
        config = {"app": {"telegram": {"listen": True, "auth_keyword": "auth"}}}
        notify.send(config=config, username="me@x.com")
        tg_msg = tg.call_args.kwargs["message"]
        self.assertIn("Reply", tg_msg)
        self.assertNotIn("docker exec", tg_msg)
        self.assertIn("docker exec", discord.call_args.kwargs["message"])

    @patch("src.notify.notify_email", return_value=None)
    @patch("src.notify.notify_pushover", return_value=None)
    @patch("src.notify.notify_discord", return_value=None)
    @patch("src.notify.notify_telegram", return_value=None)
    def test_listen_off_sends_standard_to_telegram(self, tg, _discord, _push, _email):
        """Listen off: Telegram gets the standard 'run docker exec' message (unchanged)."""
        config = {"app": {"telegram": {}}}
        notify.send(config=config, username="me@x.com")
        self.assertIn("docker exec", tg.call_args.kwargs["message"])


class TestWaitForTelegramCode(unittest.TestCase):
    """sync._wait_for_telegram_code -- the manual-trigger 2FA poll loop."""

    def setUp(self):
        self.config = {"app": {"telegram": {"bot_token": "t", "chat_id": "c"}}}
        self.api = MagicMock()

    @patch("src.sync.sleep")
    def test_missing_credentials_falls_back_to_sleep(self, mock_sleep):
        """Without bot_token/chat_id the loop just sleeps and reports failure."""
        result = sync._wait_for_telegram_code(config={"app": {"telegram": {}}}, api=self.api, timeout_seconds=42)  # noqa: SLF001
        self.assertFalse(result)
        mock_sleep.assert_called_once_with(42)

    @patch("src.notify.post_message_to_telegram")
    @patch("src.notify.poll_telegram_for_text")
    @patch("src.sync.sleep")
    def test_auth_keyword_triggers_push(self, _sleep, poll, post):
        """Replying the keyword requests a 2FA push and confirms success."""
        self.api.trigger_2fa_push_notification.return_value = True
        poll.side_effect = [(None, 0), (None, 0), ("auth", 5)]
        result = sync._wait_for_telegram_code(config=self.config, api=self.api, timeout_seconds=5)  # noqa: SLF001
        self.assertFalse(result)  # push sent, but no code arrived before timeout
        self.api.trigger_2fa_push_notification.assert_called_once()
        self.assertTrue(any("code sent" in c.args[2] for c in post.call_args_list))

    @patch("src.notify.post_message_to_telegram")
    @patch("src.notify.poll_telegram_for_text")
    @patch("src.sync.sleep")
    def test_auth_keyword_push_failure_is_reported(self, _sleep, poll, post):
        """A failed push trigger tells the user, non-fatally."""
        self.api.trigger_2fa_push_notification.side_effect = RuntimeError("no device")
        poll.side_effect = [(None, 0), (None, 0), ("AUTH", 5)]
        result = sync._wait_for_telegram_code(config=self.config, api=self.api, timeout_seconds=5)  # noqa: SLF001
        self.assertFalse(result)
        self.assertTrue(any("Couldn't request" in c.args[2] for c in post.call_args_list))

    @patch("src.notify.post_message_to_telegram")
    @patch("src.notify.poll_telegram_for_text")
    @patch("src.sync.sleep")
    def test_valid_code_validates_and_trusts(self, _sleep, poll, post):
        """A 6-digit reply validates, trusts the session, and returns True."""
        self.api.validate_2fa_code.return_value = True
        # drain advances the offset (0 -> 5), then a blank, then the code arrives
        poll.side_effect = [(None, 0), (None, 5), (None, 5), (None, 5), ("123456", 6)]
        result = sync._wait_for_telegram_code(config=self.config, api=self.api, timeout_seconds=10)  # noqa: SLF001
        self.assertTrue(result)
        self.api.validate_2fa_code.assert_called_once_with("123456")
        self.api.trust_session.assert_called_once()
        self.assertTrue(any("Re-authenticated" in c.args[2] for c in post.call_args_list))

    @patch("src.notify.post_message_to_telegram")
    @patch("src.notify.poll_telegram_for_text")
    @patch("src.sync.sleep")
    def test_code_with_spaces_is_accepted(self, _sleep, poll, _post):
        """A code pasted as '123 456' is normalised and validated."""
        self.api.validate_2fa_code.return_value = True
        poll.side_effect = [(None, 0), (None, 0), ("123 456", 6)]
        result = sync._wait_for_telegram_code(config=self.config, api=self.api, timeout_seconds=5)  # noqa: SLF001
        self.assertTrue(result)
        self.api.validate_2fa_code.assert_called_once_with("123456")

    @patch("src.notify.post_message_to_telegram")
    @patch("src.notify.poll_telegram_for_text")
    @patch("src.sync.sleep")
    def test_rejected_code_asks_for_another(self, _sleep, poll, post):
        """Apple rejecting the code prompts for a fresh one."""
        self.api.validate_2fa_code.return_value = False
        poll.side_effect = [(None, 0), (None, 0), ("123456", 6)]
        result = sync._wait_for_telegram_code(config=self.config, api=self.api, timeout_seconds=5)  # noqa: SLF001
        self.assertFalse(result)
        self.assertTrue(any("rejected" in c.args[2] for c in post.call_args_list))

    @patch("src.notify.post_message_to_telegram")
    @patch("src.notify.poll_telegram_for_text")
    @patch("src.sync.sleep")
    def test_validate_raises_keeps_waiting(self, _sleep, poll, _post):
        """An exception from validate_2fa_code is swallowed; the loop keeps waiting."""
        self.api.validate_2fa_code.side_effect = RuntimeError("api down")
        poll.side_effect = [(None, 0), (None, 0), ("123456", 6)]
        result = sync._wait_for_telegram_code(config=self.config, api=self.api, timeout_seconds=5)  # noqa: SLF001
        self.assertFalse(result)
        self.api.trust_session.assert_not_called()

    @patch("src.notify.post_message_to_telegram")
    @patch("src.notify.poll_telegram_for_text")
    @patch("src.sync.sleep")
    def test_trust_session_failure_is_non_fatal(self, _sleep, poll, post):
        """trust_session raising still counts as a successful re-auth."""
        self.api.validate_2fa_code.return_value = True
        self.api.trust_session.side_effect = RuntimeError("trust glitch")
        poll.side_effect = [(None, 0), (None, 0), ("123456", 6)]
        result = sync._wait_for_telegram_code(config=self.config, api=self.api, timeout_seconds=5)  # noqa: SLF001
        self.assertTrue(result)
        self.assertTrue(any("Re-authenticated" in c.args[2] for c in post.call_args_list))

    @patch("src.notify.post_message_to_telegram")
    @patch("src.notify.poll_telegram_for_text")
    @patch("src.sync.sleep")
    def test_unrelated_text_is_ignored_until_timeout(self, _sleep, poll, _post):
        """Replies that are neither keyword nor 6-digit are ignored."""
        poll.side_effect = [(None, 0), (None, 0), ("hello there", 5)]
        result = sync._wait_for_telegram_code(config=self.config, api=self.api, timeout_seconds=5)  # noqa: SLF001
        self.assertFalse(result)
        self.api.trigger_2fa_push_notification.assert_not_called()


class TestHandle2faRequiredTelegramBranch(unittest.TestCase):
    """sync._handle_2fa_required -- telegram branch wiring."""

    @patch("src.sync.notify.send", return_value=None)
    @patch("src.config_parser.get_retry_login_interval", return_value=-1)
    def test_negative_interval_exits(self, _interval, _send):
        """A negative retry interval signals exit (return False)."""
        self.assertFalse(sync._handle_2fa_required({}, "user", SyncState(), api=MagicMock()))  # noqa: SLF001

    @patch("src.sync._wait_for_telegram_code")  # noqa: SLF001
    @patch("src.sync.notify.send", return_value=None)
    @patch("src.config_parser.get_retry_login_interval", return_value=60)
    def test_listen_enabled_uses_telegram_wait(self, _interval, mock_send, mock_wait):
        """With api + listen enabled, notify.send fires (throttled prompt) then the wait runs."""
        config = {"app": {"telegram": {"bot_token": "t", "chat_id": "c", "listen": True}}}
        result = sync._handle_2fa_required(config, "user", SyncState(), api=MagicMock())  # noqa: SLF001
        self.assertTrue(result)
        mock_send.assert_called_once()
        mock_wait.assert_called_once()

    @patch("src.sync.sleep")
    @patch("src.sync.notify.send", return_value=None)
    @patch("src.config_parser.get_retry_login_interval", return_value=60)
    def test_without_api_falls_back_to_sleep(self, _interval, mock_send, mock_sleep):
        """No api (or listen off) keeps the original sleep + standard notification."""
        result = sync._handle_2fa_required({"app": {"telegram": {}}}, "user", SyncState(), api=None)  # noqa: SLF001
        self.assertTrue(result)
        mock_sleep.assert_called_once_with(60)
        mock_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
