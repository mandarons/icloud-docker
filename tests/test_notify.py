"""Test for notify.py file."""

import datetime
import unittest
from email import message_from_string
from unittest.mock import Mock, patch

import requests

from src import config_parser, notify
from src.email_message import EmailMessage as Message
from src.notify import (
    notify_discord,
    notify_pushover,
    notify_telegram,
    post_message_to_discord,
    post_message_to_pushover,
    post_message_to_telegram,
)


class TestNotify(unittest.TestCase):
    """Tests class for notify.py file."""

    def setUp(self) -> None:
        """Initialize tests."""
        self.config = {
            "app": {
                "smtp": {
                    "email": "user@test.com",
                    "to": "to@email.com",
                    "host": "smtp.test.com",
                    "port": "587",
                    "password": "password",
                },
                "telegram": {"bot_token": "bot_token", "chat_id": "chat_id"},
                "pushover": {"user_key": "pushover_user_key", "api_token": "pushover_api_token"},
            },
        }
        self.message_body = "message body"

    def test_throttling(self):
        """Test for throttled notification."""
        not_24_hours = datetime.datetime.now()
        # if less than 24 hours has passed since last send, then the same
        # datetime object is returned
        self.assertEqual(
            not_24_hours,
            notify.send(self.config, "username@icloud.com", not_24_hours, dry_run=True),
        )

    def test_no_smtp_config(self):
        """Test for None is returned if email didn't send because of missing config."""
        self.assertIsNone(notify.send({}, None, dry_run=True))

    def test_dry_run_send(self):
        """Test for send returns the datetime of the request."""
        self.assertIsInstance(notify.send(self.config, None, dry_run=True), datetime.datetime)

    def test_build_message(self):
        """Test for building a valid email."""
        subject = "icloud-docker: Two step authentication required"
        message = "Two-step authentication for iCloud Drive, Photos (Docker) is required."

        msg = notify.build_message(
            email=self.config["app"]["smtp"]["email"],
            to_email=self.config["app"]["smtp"]["to"],
            subject=subject,
            message=message,
        )
        self.assertEqual(msg.to, self.config["app"]["smtp"]["to"])
        self.assertIsNotNone(msg.sender)
        assert msg.sender is not None
        self.assertIn(self.config["app"]["smtp"]["email"], msg.sender)
        self.assertIn(subject, msg.subject)
        self.assertIsNotNone(msg.body)
        assert msg.body is not None
        self.assertIn(
            message,
            msg.body,
        )
        self.assertIsInstance(msg, Message)

    def test_build_message_with_unicode(self):
        """Unicode content should automatically switch email charset to UTF-8."""
        subject = "Sync ✅"
        message = "✅ Sync completed"

        msg = notify.build_message(
            email=self.config["app"]["smtp"]["email"],
            to_email=self.config["app"]["smtp"]["to"],
            subject=subject,
            message=message,
        )

        self.assertEqual(msg.charset, "utf-8")
        self.assertEqual(msg.body, message)

    def test_contains_non_ascii_handles_none(self):
        """Helper should treat None as ASCII safe."""

        self.assertFalse(notify._contains_non_ascii(None))  # noqa: SLF001

    def test_send(self):
        """Test for email send."""
        username = "username@icloud.com"
        with (
            patch("smtplib.SMTP") as smtp,
            patch("src.notify.post_message_to_telegram"),
            patch("src.notify.post_message_to_discord"),
            patch("src.notify.post_message_to_pushover"),
        ):
            notify.send(self.config, username=username)

            instance = smtp.return_value

            # verify that sendmail() was called
            self.assertTrue(instance.sendmail.called)
            self.assertEqual(instance.sendmail.call_count, 1)

            # verify that the correct email is being sent to sendmail()
            self.assertEqual(
                config_parser.get_smtp_email(config=self.config),
                instance.sendmail.mock_calls[0][2]["from_addr"],
            )
            self.assertEqual(
                config_parser.get_smtp_to_email(config=self.config),
                instance.sendmail.mock_calls[0][2]["to_addrs"],
            )

            # verify that the message was passed to sendmail()
            self.assertIn(
                "Subject: icloud-docker: iCloud login required for",
                instance.sendmail.mock_calls[0][2]["msg"],
            )

    def test_send_email_no_throttle_handles_unicode(self):
        """Ensure UTF-8 emails send successfully when body contains emojis."""

        class DummySMTP:
            def __init__(self) -> None:
                self.sent_messages = []

            def sendmail(self, from_addr, to_addrs, msg):  # noqa: ANN001
                self.sent_messages.append((from_addr, to_addrs, msg))

            def quit(self) -> None:
                return None

        dummy_smtp = DummySMTP()

        with (
            patch("src.notify._get_smtp_config") as mock_get_config,
            patch("src.notify._create_smtp_connection", return_value=dummy_smtp),
            patch("src.notify._authenticate_smtp") as mock_auth,
        ):
            mock_get_config.return_value = (
                self.config["app"]["smtp"]["email"],
                self.config["app"]["smtp"]["to"],
                "smtp.test.com",
                587,
                False,
                None,
                "password",
                True,
            )

            result = notify._send_email_no_throttle(  # noqa: SLF001
                self.config,
                "✅ Sync completed",
                "Sync ✅",
                dry_run=False,
            )

        self.assertTrue(result)
        mock_auth.assert_called_once()
        self.assertEqual(len(dummy_smtp.sent_messages), 1)

        sent_message = dummy_smtp.sent_messages[0][2]
        parsed = message_from_string(sent_message)
        payload_raw = parsed.get_payload(decode=True)
        self.assertIsInstance(payload_raw, (bytes, bytearray))
        payload_bytes = bytes(payload_raw)
        charset = parsed.get_content_charset() or "utf-8"
        payload = payload_bytes.decode(charset)

        self.assertIn("✅", payload)
        self.assertEqual(parsed.get_content_charset(), "utf-8")

    def test_send_with_username(self):
        """Test for email send."""
        username = "username@icloud.com"
        with (
            patch("smtplib.SMTP") as smtp,
            patch("src.notify.post_message_to_telegram"),
            patch("src.notify.post_message_to_discord"),
            patch("src.notify.post_message_to_pushover"),
        ):
            self.config["app"]["smtp"]["username"] = "smtp-username"
            notify.send(self.config, username)

            instance = smtp.return_value

            # verify that sendmail() was called
            self.assertTrue(instance.sendmail.called)
            self.assertEqual(instance.sendmail.call_count, 1)

            # verify that the correct email is being sent to sendmail()
            self.assertEqual(
                config_parser.get_smtp_email(config=self.config),
                instance.sendmail.mock_calls[0][2]["from_addr"],
            )
            self.assertEqual(
                config_parser.get_smtp_to_email(config=self.config),
                instance.sendmail.mock_calls[0][2]["to_addrs"],
            )

            # verify that the message was passed to sendmail()
            self.assertIn(
                "Subject: icloud-docker: iCloud login required for",
                instance.sendmail.mock_calls[0][2]["msg"],
            )
            self.assertNotIn("--region=", instance.sendmail.mock_calls[0][2]["msg"])

    def test_send_with_region(self):
        """Test for email send with region."""
        username = "username@icloud.com"
        with (
            patch("smtplib.SMTP") as smtp,
            patch("src.notify.post_message_to_telegram"),
            patch("src.notify.post_message_to_discord"),
            patch("src.notify.post_message_to_pushover"),
        ):
            notify.send(self.config, username, region="some_region")

            instance = smtp.return_value
            self.assertIn("--region=some_region", instance.sendmail.mock_calls[0][2]["msg"])

    def test_send_fail(self):
        """Test for failed send."""
        username = "username@icloud.com"
        with (
            patch("smtplib.SMTP") as smtp,
            patch("src.notify.post_message_to_telegram") as telegram_mock,
            patch("src.notify.post_message_to_discord") as discord_mock,
            patch("src.notify.post_message_to_pushover") as pushover_mock,
        ):
            smtp.side_effect = Exception
            # Make all notification methods return False (failure)
            telegram_mock.return_value = False
            discord_mock.return_value = False
            pushover_mock.return_value = False

            # Verify that a failure doesn't return a send_on timestamp
            sent_on = notify.send(self.config, username)
            self.assertEqual(None, sent_on)

    def test_notify_telegram_success(self):
        """Test for successful notification."""
        config = {"app": {"telegram": {"bot_token": "your-bot-token", "chat_id": "your-chat-id"}}}

        with patch("src.notify.post_message_to_telegram") as post_message_mock:
            notify_telegram(config, self.message_body, None, False)

            # Verify that post_message_to_telegram is called with the correct arguments
            post_message_mock.assert_called_once_with(
                config["app"]["telegram"]["bot_token"],
                config["app"]["telegram"]["chat_id"],
                self.message_body,
            )

    def test_notify_telegram_fail(self):
        """Test for failed notification."""
        config = {"app": {"telegram": {"bot_token": "your-bot-token", "chat_id": "your-chat-id"}}}

        with patch("src.notify.post_message_to_telegram") as post_message_mock:
            post_message_mock.return_value = False
            notify_telegram(config, self.message_body, None, False)

            # Verify that post_message_to_telegram is called with the correct arguments
            post_message_mock.assert_called_once_with(
                config["app"]["telegram"]["bot_token"],
                config["app"]["telegram"]["chat_id"],
                self.message_body,
            )

    def test_notify_telegram_throttling(self):
        """Test for throttled notification."""
        config = {"telegram": {"bot_token": "your-bot-token", "chat_id": "your-chat-id"}}
        last_send = datetime.datetime.now() - datetime.timedelta(hours=2)
        dry_run = False

        with patch("src.notify.post_message_to_telegram") as post_message_mock:
            notify_telegram(config, last_send, dry_run)

            # Verify that post_message_to_telegram is not called when throttled
            post_message_mock.assert_not_called()

    def test_notify_telegram_dry_run(self):
        """Test for dry run mode."""
        config = {"telegram": {"bot_token": "your-bot-token", "chat_id": "your-chat-id"}}
        last_send = datetime.datetime.now()
        dry_run = True

        with patch("src.notify.post_message_to_telegram") as post_message_mock:
            notify_telegram(config, self.message_body, last_send, dry_run)

            # Verify that post_message_to_telegram is not called in dry run mode
            post_message_mock.assert_not_called()

    def test_notify_telegram_no_config(self):
        """Test for missing telegram configuration."""
        config = {}
        last_send = None
        dry_run = False

        with patch("src.notify.post_message_to_telegram") as post_message_mock:
            notify_telegram(config, last_send, dry_run)

            # Verify that post_message_to_telegram is not called when telegram configuration is missing
            post_message_mock.assert_not_called()

    def test_post_message_to_telegram(self):
        """Test for successful post."""
        with patch("requests.post") as post_mock:
            post_mock.return_value.status_code = 200
            post_message_to_telegram("bot_token", "chat_id", "message")

            # Verify that post is called with the correct arguments
            post_mock.assert_called_once_with(
                "https://api.telegram.org/botbot_token/sendMessage",
                params={"chat_id": "chat_id", "text": "message"},
                timeout=10,
            )

    def test_post_message_to_telegram_fail(self):
        """Test for failed post."""
        with patch("requests.post") as post_mock:
            post_mock.return_value.status_code = 400
            post_message_to_telegram("bot_token", "chat_id", "message")

            # Verify that post is called with the correct arguments
            post_mock.assert_called_once_with(
                "https://api.telegram.org/botbot_token/sendMessage",
                params={"chat_id": "chat_id", "text": "message"},
                timeout=10,
            )

    def test_notify_discord_success(self):
        """Test for successful notification."""
        config = {"app": {"discord": {"webhook_url": "webhook-url", "username": "username"}}}

        with patch("src.notify.post_message_to_discord") as post_message_mock:
            notify_discord(config, self.message_body, None, False)

            # Verify that post_message_to_discord is called with the correct arguments
            post_message_mock.assert_called_once_with(
                config["app"]["discord"]["webhook_url"],
                config["app"]["discord"]["username"],
                self.message_body,
            )
            self.assertEqual(post_message_mock.call_count, 1)

    def test_notify_discord_fail(self):
        """Test for failed notification."""
        config = {"app": {"discord": {"webhook_url": "webhook-url", "username": "username"}}}

        with patch("src.notify.post_message_to_discord") as post_message_mock:
            post_message_mock.return_value = False
            notify_discord(config, self.message_body, None, False)

            # Verify that post_message_to_discord is called with the correct arguments
            post_message_mock.assert_called_once_with(
                config["app"]["discord"]["webhook_url"],
                config["app"]["discord"]["username"],
                self.message_body,
            )

    def test_notify_discord_throttling(self):
        """Test for throttled notification."""
        config = {"app": {"discord": {"webhook_url": "webhook-url", "username": "username"}}}
        last_send = datetime.datetime.now() - datetime.timedelta(hours=2)
        dry_run = False

        with patch("src.notify.post_message_to_discord") as post_message_mock:
            notify_discord(config, self.message_body, last_send, dry_run)

            # Verify that post_message_to_discord is not called when throttled
            post_message_mock.assert_not_called()

    def test_send_sync_summary_disabled(self):
        """Test that sync summary is not sent when disabled."""
        from src.sync_stats import DriveStats, SyncSummary

        config = {"app": {"notifications": {"sync_summary": {"enabled": False}}}}
        summary = SyncSummary(drive_stats=DriveStats(files_downloaded=5))

        result = notify.send_sync_summary(config, summary)
        self.assertFalse(result)

    def test_send_sync_summary_no_activity(self):
        """Test that sync summary is not sent when there's no activity."""
        from src.sync_stats import SyncSummary

        config = {"app": {"notifications": {"sync_summary": {"enabled": True}}}}
        summary = SyncSummary()  # No activity

        result = notify.send_sync_summary(config, summary)
        self.assertFalse(result)

    def test_send_sync_summary_success(self):
        """Test successful sync summary send."""
        from src.sync_stats import DriveStats, SyncSummary

        config = {
            "app": {
                "notifications": {
                    "sync_summary": {"enabled": True, "on_success": True, "min_downloads": 1},
                },
                "telegram": {"bot_token": "bot_token", "chat_id": "chat_id"},
            },
        }
        summary = SyncSummary(drive_stats=DriveStats(files_downloaded=5, bytes_downloaded=1024000))

        with patch("src.notify.post_message_to_telegram") as post_mock:
            post_mock.return_value = True
            result = notify.send_sync_summary(config, summary)
            self.assertTrue(result)
            post_mock.assert_called_once()

    def test_send_sync_summary_with_errors(self):
        """Test sync summary with errors."""
        from src.sync_stats import DriveStats, PhotoStats, SyncSummary

        config = {
            "app": {
                "notifications": {
                    "sync_summary": {"enabled": True, "on_error": True, "min_downloads": 0},
                },
                "telegram": {"bot_token": "bot_token", "chat_id": "chat_id"},
            },
        }
        summary = SyncSummary(
            drive_stats=DriveStats(files_downloaded=5, errors=["Error 1"]),
            photo_stats=PhotoStats(photos_downloaded=3, errors=["Error 2"]),
        )

        with patch("src.notify.post_message_to_telegram") as post_mock:
            post_mock.return_value = True
            result = notify.send_sync_summary(config, summary)
            self.assertTrue(result)
            post_mock.assert_called_once()

    def test_send_sync_summary_min_downloads_threshold(self):
        """Test that sync summary respects min_downloads threshold."""
        from src.sync_stats import DriveStats, SyncSummary

        config = {
            "app": {
                "notifications": {
                    "sync_summary": {"enabled": True, "on_success": True, "min_downloads": 10},
                },
            },
        }
        # Only 5 downloads, below threshold of 10
        summary = SyncSummary(drive_stats=DriveStats(files_downloaded=5))

        result = notify.send_sync_summary(config, summary)
        self.assertFalse(result)

    def test_send_sync_summary_on_success_false(self):
        """Test that sync summary is not sent on success when on_success is False."""
        from src.sync_stats import DriveStats, SyncSummary

        config = {
            "app": {
                "notifications": {
                    "sync_summary": {"enabled": True, "on_success": False, "on_error": True, "min_downloads": 1},
                },
            },
        }
        # Successful sync (no errors)
        summary = SyncSummary(drive_stats=DriveStats(files_downloaded=5))

        result = notify.send_sync_summary(config, summary)
        self.assertFalse(result)

    def test_send_sync_summary_dry_run(self):
        """Test sync summary in dry run mode."""
        from src.sync_stats import DriveStats, SyncSummary

        config = {
            "app": {
                "notifications": {
                    "sync_summary": {"enabled": True, "on_success": True, "min_downloads": 1},
                },
                "telegram": {"bot_token": "bot_token", "chat_id": "chat_id"},
            },
        }
        summary = SyncSummary(drive_stats=DriveStats(files_downloaded=5))

        with patch("src.notify.post_message_to_telegram") as post_mock:
            result = notify.send_sync_summary(config, summary, dry_run=True)
            self.assertTrue(result)
            # In dry run, function should not be called
            post_mock.assert_not_called()

    def test_format_sync_summary_message(self):
        """Test formatting of sync summary message."""
        from src.notify import _format_sync_summary_message
        from src.sync_stats import DriveStats, PhotoStats, SyncSummary

        summary = SyncSummary(
            drive_stats=DriveStats(
                files_downloaded=15,
                files_skipped=234,
                bytes_downloaded=2415919104,
                duration_seconds=272,
            ),
            photo_stats=PhotoStats(
                photos_downloaded=42,
                photos_hardlinked=128,
                bytes_downloaded=1932735283,
                bytes_saved_by_hardlinks=5798205849,
                albums_synced=["All Photos", "Favorites", "Family"],
                duration_seconds=135,
            ),
        )

        message, subject = _format_sync_summary_message(summary)

        # Check subject
        self.assertIn("Sync Complete", subject)

        # Check message contains expected sections
        self.assertIn("✅", message)
        self.assertIn("📁 Drive:", message)
        self.assertIn("Downloaded: 15 files", message)
        self.assertIn("Skipped: 234 files", message)
        self.assertIn("📷 Photos:", message)
        self.assertIn("Downloaded: 42 photos", message)
        self.assertIn("Hard-linked: 128 photos", message)
        self.assertIn("Storage saved:", message)
        self.assertIn("Albums: All Photos, Favorites, Family", message)

    def test_format_sync_summary_message_with_errors(self):
        """Test formatting of sync summary message with errors."""
        from src.notify import _format_sync_summary_message
        from src.sync_stats import DriveStats, SyncSummary

        summary = SyncSummary(
            drive_stats=DriveStats(
                files_downloaded=3,
                errors=["/path/file1.txt (timeout)", "/path/file2.pdf (API error)"],
            ),
        )

        message, subject = _format_sync_summary_message(summary)

        # Check subject indicates errors
        self.assertIn("Completed with Errors", subject)

        # Check message contains error indicator
        self.assertIn("⚠️", message)
        self.assertIn("Failed items:", message)
        self.assertIn("/path/file1.txt", message)

    def test_format_sync_summary_message_with_removed_files(self):
        """Test formatting message with removed files."""
        from src.notify import _format_sync_summary_message
        from src.sync_stats import DriveStats, SyncSummary

        summary = SyncSummary(
            drive_stats=DriveStats(files_downloaded=5, files_removed=3, bytes_downloaded=1048576, duration_seconds=60),
        )

        message, subject = _format_sync_summary_message(summary)

        # Check message contains removed files
        self.assertIn("Removed: 3 obsolete files", message)

    def test_format_sync_summary_message_with_many_albums(self):
        """Test formatting message with more than 5 albums."""
        from src.notify import _format_sync_summary_message
        from src.sync_stats import PhotoStats, SyncSummary

        summary = SyncSummary(
            photo_stats=PhotoStats(
                photos_downloaded=10,
                albums_synced=["Album1", "Album2", "Album3", "Album4", "Album5", "Album6", "Album7"],
                duration_seconds=120,
            ),
        )

        message, subject = _format_sync_summary_message(summary)

        # Check message truncates albums list
        self.assertIn("Album1, Album2, Album3, Album4, Album5 (+2 more)", message)

    def test_send_telegram_no_throttle_successful_send(self):
        """Test _send_telegram_no_throttle with successful send."""
        from src.notify import _send_telegram_no_throttle

        config = {"app": {"telegram": {"bot_token": "bot_token", "chat_id": "chat_id"}}}

        with patch("src.notify.post_message_to_telegram") as mock_post:
            mock_post.return_value = True
            result = _send_telegram_no_throttle(config, "test message", dry_run=False)
            self.assertTrue(result)
            mock_post.assert_called_once()

    def test_send_telegram_no_throttle_not_configured(self):
        """Test _send_telegram_no_throttle when not configured."""
        from src.notify import _send_telegram_no_throttle

        config = {}
        result = _send_telegram_no_throttle(config, "test message", dry_run=False)
        self.assertFalse(result)

    def test_send_telegram_no_throttle_dry_run(self):
        """Test _send_telegram_no_throttle in dry run mode."""
        from src.notify import _send_telegram_no_throttle

        config = {"app": {"telegram": {"bot_token": "bot_token", "chat_id": "chat_id"}}}

        with patch("src.notify.post_message_to_telegram") as mock_post:
            result = _send_telegram_no_throttle(config, "test message", dry_run=True)
            self.assertTrue(result)
            mock_post.assert_not_called()

    def test_send_discord_no_throttle_success(self):
        """Test _send_discord_no_throttle with successful send."""
        from src.notify import _send_discord_no_throttle

        config = {"app": {"discord": {"webhook_url": "webhook_url", "username": "username"}}}

        with patch("src.notify.post_message_to_discord") as mock_post:
            mock_post.return_value = True
            result = _send_discord_no_throttle(config, "test message", dry_run=False)
            self.assertTrue(result)
            mock_post.assert_called_once()

    def test_send_discord_no_throttle_dry_run(self):
        """Test _send_discord_no_throttle in dry run mode."""
        from src.notify import _send_discord_no_throttle

        config = {"app": {"discord": {"webhook_url": "webhook_url", "username": "username"}}}

        with patch("src.notify.post_message_to_discord") as mock_post:
            result = _send_discord_no_throttle(config, "test message", dry_run=True)
            self.assertTrue(result)
            mock_post.assert_not_called()

    def test_send_pushover_no_throttle_success(self):
        """Test _send_pushover_no_throttle with successful send."""
        from src.notify import _send_pushover_no_throttle

        config = {"app": {"pushover": {"user_key": "user_key", "api_token": "api_token"}}}

        with patch("src.notify.post_message_to_pushover") as mock_post:
            mock_post.return_value = True
            result = _send_pushover_no_throttle(config, "test message", dry_run=False)
            self.assertTrue(result)
            mock_post.assert_called_once()

    def test_send_pushover_no_throttle_dry_run(self):
        """Test _send_pushover_no_throttle in dry run mode."""
        from src.notify import _send_pushover_no_throttle

        config = {"app": {"pushover": {"user_key": "user_key", "api_token": "api_token"}}}

        with patch("src.notify.post_message_to_pushover") as mock_post:
            result = _send_pushover_no_throttle(config, "test message", dry_run=True)
            self.assertTrue(result)
            mock_post.assert_not_called()

    def test_send_email_no_throttle_success(self):
        """Test _send_email_no_throttle with successful send."""
        from src.notify import _send_email_no_throttle

        config = {
            "app": {
                "smtp": {
                    "email": "test@example.com",
                    "to": "recipient@example.com",
                    "host": "smtp.example.com",
                    "port": 587,
                    "password": "password",
                },
            },
        }

        with patch("smtplib.SMTP") as mock_smtp:
            result = _send_email_no_throttle(config, "test message", "test subject", dry_run=False)
            self.assertTrue(result)
            mock_smtp.assert_called_once()

    def test_send_email_no_throttle_dry_run(self):
        """Test _send_email_no_throttle in dry run mode."""
        from src.notify import _send_email_no_throttle

        config = {
            "app": {
                "smtp": {
                    "email": "test@example.com",
                    "to": "recipient@example.com",
                    "host": "smtp.example.com",
                    "port": 587,
                },
            },
        }

        with patch("smtplib.SMTP") as mock_smtp:
            result = _send_email_no_throttle(config, "test message", "test subject", dry_run=True)
            self.assertTrue(result)
            mock_smtp.assert_not_called()

    def test_send_email_no_throttle_exception(self):
        """Test _send_email_no_throttle with exception."""
        from src.notify import _send_email_no_throttle

        config = {
            "app": {
                "smtp": {
                    "email": "test@example.com",
                    "to": "recipient@example.com",
                    "host": "smtp.example.com",
                    "port": 587,
                },
            },
        }

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = Exception("Test exception")
            result = _send_email_no_throttle(config, "test message", "test subject", dry_run=False)
            self.assertFalse(result)

    def test_notify_discord_dry_run(self):
        """Test for dry run mode."""
        config = {"app": {"discord": {"webhook_url": "webhook-url", "username": "username"}}}
        last_send = datetime.datetime.now()
        dry_run = True

        with patch("src.notify.post_message_to_discord") as post_message_mock:
            notify_discord(config, self.message_body, last_send, dry_run)

            # Verify that post_message_to_discord is not called in dry run mode
            post_message_mock.assert_not_called()

    def test_notify_discord_no_config(self):
        """Test for missing discord configuration."""
        config = {}
        last_send = None
        dry_run = False

        with patch("src.notify.post_message_to_discord") as post_message_mock:
            notify_discord(config, last_send, dry_run)

            # Verify that post_message_to_discord is not called when discord configuration is missing
            post_message_mock.assert_not_called()

    def test_post_message_to_discord(self):
        """Test for successful post."""
        message = "message"
        with patch("requests.post") as post_mock:
            post_mock.return_value.status_code = 204
            post_message_to_discord("webhook_url", "username", message)

            # Verify that post is called with the correct arguments
            post_mock.assert_called_once_with(
                "webhook_url",
                data={"content": message, "username": "username"},
                timeout=10,
            )

    def test_post_message_to_discord_fail(self):
        """Test for failed post."""
        message = "discord message"
        with patch("requests.post") as post_mock:
            post_mock.return_value.status_code = 400
            post_message_to_discord("webhook_url", "username", message)

            # Verify that post is called with the correct arguments
            post_mock.assert_called_once_with(
                "webhook_url",
                data={"content": message, "username": "username"},
                timeout=10,
            )

    def test_notify_pushover_success(self):
        """Test for successful Pushover notification."""
        with patch("src.notify.post_message_to_pushover") as post_message_mock:
            notify_pushover(self.config, self.message_body, None, False)

            # Verify that post_message_to_pushover is called with the correct arguments
            post_message_mock.assert_called_once_with(
                self.config["app"]["pushover"]["api_token"],
                self.config["app"]["pushover"]["user_key"],
                None,
                self.message_body,
            )

    def test_notify_pushover_fail(self):
        """Test for failed Pushover notification."""
        with patch("src.notify.post_message_to_pushover") as post_message_mock:
            post_message_mock.return_value = False
            notify_pushover(self.config, self.message_body, None, False)

            # Verify that post_message_to_pushover is called with the correct arguments
            post_message_mock.assert_called_once_with(
                self.config["app"]["pushover"]["api_token"],
                self.config["app"]["pushover"]["user_key"],
                None,
                self.message_body,
            )

    def test_notify_pushover_throttling(self):
        """Test for throttled Pushover notification."""
        last_send = datetime.datetime.now() - datetime.timedelta(hours=2)
        dry_run = False

        with patch("src.notify.post_message_to_pushover") as post_message_mock:
            notify_pushover(self.config, self.message_body, last_send, dry_run)

            # Verify that post_message_to_pushover is not called when throttled
            post_message_mock.assert_not_called()

    def test_notify_pushover_dry_run(self):
        """Test for dry run mode in Pushover notification."""
        last_send = datetime.datetime.now()
        dry_run = True

        with patch("src.notify.post_message_to_pushover") as post_message_mock:
            notify_pushover(self.config, self.message_body, last_send, dry_run)

            # Verify that post_message_to_pushover is not called in dry run mode
            post_message_mock.assert_not_called()

    def test_notify_pushover_no_config(self):
        """Test for missing Pushover configuration."""
        config = {}
        last_send = None
        dry_run = False

        with patch("src.notify.post_message_to_pushover") as post_message_mock:
            notify_pushover(config, self.message_body, last_send, dry_run)

            # Verify that post_message_to_pushover is not called when Pushover configuration is missing
            post_message_mock.assert_not_called()

    def test_post_message_to_pushover(self):
        """Test for successful post to Pushover."""
        with patch("requests.post") as post_mock:
            post_mock.return_value.status_code = 200
            post_message_to_pushover("pushover_api_token", "pushover_user_key", None, "message")

            # Verify that post is called with the correct arguments
            post_mock.assert_called_once_with(
                "https://api.pushover.net/1/messages.json",
                data={"token": "pushover_api_token", "user": "pushover_user_key", "message": "message"},
                timeout=10,
            )

    def test_post_message_to_pushover_fail(self):
        """Test for failed post to Pushover."""
        with patch("requests.post") as post_mock:
            post_mock.return_value.status_code = 400
            post_message_to_pushover("pushover_api_token", "pushover_user_key", None, "message")

            # Verify that post is called with the correct arguments
            post_mock.assert_called_once_with(
                "https://api.pushover.net/1/messages.json",
                data={"token": "pushover_api_token", "user": "pushover_user_key", "message": "message"},
                timeout=10,
            )

    def test_post_message_to_pushover_with_priority(self):
        """Test for post to Pushover with priority."""
        with patch("requests.post") as post_mock:
            post_mock.return_value.status_code = 200
            post_message_to_pushover("pushover_api_token", "pushover_user_key", 1, "message")

            # Verify that post is called with the correct arguments including priority
            post_mock.assert_called_once_with(
                "https://api.pushover.net/1/messages.json",
                data={"token": "pushover_api_token", "user": "pushover_user_key", "message": "message", "priority": 1},
                timeout=10,
            )

    def test_post_message_to_pushover_with_priority_zero(self):
        """Test for post to Pushover with priority zero."""
        with patch("requests.post") as post_mock:
            post_mock.return_value.status_code = 200
            post_message_to_pushover("pushover_api_token", "pushover_user_key", 0, "message")

            # Verify that post is called with priority=0 (should not be excluded due to truthiness check)
            post_mock.assert_called_once_with(
                "https://api.pushover.net/1/messages.json",
                data={"token": "pushover_api_token", "user": "pushover_user_key", "message": "message", "priority": 0},
                timeout=10,
            )

    def test_format_sync_summary_message_with_many_errors(self):
        """Test formatting message with more than 10 errors."""
        from src.notify import _format_sync_summary_message
        from src.sync_stats import DriveStats, PhotoStats, SyncSummary

        # Create 15 errors total (8 from drive, 7 from photos)
        drive_errors = [f"/drive/file{i}.txt (error)" for i in range(8)]
        photo_errors = [f"/photos/img{i}.jpg (error)" for i in range(7)]

        summary = SyncSummary(
            drive_stats=DriveStats(files_downloaded=1, errors=drive_errors),
            photo_stats=PhotoStats(photos_downloaded=1, errors=photo_errors),
        )

        message, subject = _format_sync_summary_message(summary)

        # Check message shows truncation
        self.assertIn("... and 5 more errors", message)

    def test_should_send_sync_summary_errors_disabled(self):
        """Test _should_send_sync_summary when on_error is False."""
        from src.notify import _should_send_sync_summary
        from src.sync_stats import DriveStats, SyncSummary

        config = {
            "app": {
                "notifications": {
                    "sync_summary": {
                        "enabled": True,
                        "on_success": True,
                        "on_error": False,  # Errors disabled
                        "min_downloads": 0,
                    },
                },
            },
        }

        # Summary with errors
        summary = SyncSummary(drive_stats=DriveStats(files_downloaded=5, errors=["error1"]))

        result = _should_send_sync_summary(config, summary)
        self.assertFalse(result)  # Should not send because has errors but on_error is False


class TestSyncLifecycleWebhooks(unittest.TestCase):
    """A ping URL is the whole credential, so the one thing these tests
    guard beyond "it does a GET" is that no failure path logs it."""

    URL = "https://hc-ping.com/11111111-2222-3333-4444-555555555555"

    def test_nothing_is_sent_when_no_url_is_configured(self):
        """The common case: three events are consulted every cycle and a user
        with no webhooks configured must pay nothing for it."""
        with patch("src.notify.requests.get") as get_mock:
            self.assertFalse(notify.ping_webhook({}, "success"))
            get_mock.assert_not_called()

    def test_a_configured_url_is_fetched_with_a_timeout(self):
        config = {"app": {"webhooks": {"success": self.URL}}}
        with patch("src.notify.requests.get") as get_mock:
            get_mock.return_value = Mock(ok=True)
            self.assertTrue(notify.ping_webhook(config, "success"))
            get_mock.assert_called_once_with(self.URL, timeout=notify.WEBHOOK_TIMEOUT_SECONDS)

    def test_each_event_reads_its_own_url(self):
        config = {"app": {"webhooks": {"start": self.URL + "/start", "failure": self.URL + "/fail"}}}
        with patch("src.notify.requests.get") as get_mock:
            get_mock.return_value = Mock(ok=True)
            notify.ping_webhook(config, "start")
            notify.ping_webhook(config, "failure")
            self.assertFalse(notify.ping_webhook(config, "success"))
        self.assertEqual(
            [call.args[0] for call in get_mock.call_args_list],
            [self.URL + "/start", self.URL + "/fail"],
        )

    def test_a_blank_url_is_not_a_url(self):
        config = {"app": {"webhooks": {"success": "   "}}}
        with patch("src.notify.requests.get") as get_mock:
            self.assertFalse(notify.ping_webhook(config, "success"))
            get_mock.assert_not_called()

    def test_an_error_response_is_reported_without_the_url(self):
        config = {"app": {"webhooks": {"failure": self.URL}}}
        with patch("src.notify.requests.get") as get_mock, patch("src.notify.LOGGER") as logger_mock:
            get_mock.return_value = Mock(ok=False, status_code=404)
            self.assertFalse(notify.ping_webhook(config, "failure"))
        logged = " ".join(str(call) for call in logger_mock.warning.call_args_list)
        self.assertIn("failure webhook", logged)
        self.assertNotIn(self.URL, logged)

    def test_a_network_failure_is_swallowed_without_the_url(self):
        """requests' own exception text carries the full URL, which is why
        only the exception type is logged."""
        config = {"app": {"webhooks": {"start": self.URL}}}
        boom = requests.exceptions.ConnectionError(f"Failed to establish a new connection to {self.URL}")
        with patch("src.notify.requests.get", side_effect=boom), patch("src.notify.LOGGER") as logger_mock:
            self.assertFalse(notify.ping_webhook(config, "start"))
        logged = " ".join(str(call) for call in logger_mock.warning.call_args_list)
        self.assertIn("ConnectionError", logged)
        self.assertNotIn(self.URL, logged)


class TestWebhookEventTransport(unittest.TestCase):
    """The webhook is a transport in the same dispatch as Telegram and
    email, so what matters is that it inherits that dispatch's behaviour --
    the shared 24h throttle above all -- and that the payload a receiver
    parses stays the shape we documented."""

    URL = "https://receiver.test/hook"
    CONFIG = {"app": {"webhooks": {"url": URL}}}

    def _summary(self, errors=False, photos=False):
        from src.sync_stats import DriveStats, PhotoStats, SyncSummary

        summary = SyncSummary()
        drive = DriveStats(files_downloaded=5, files_skipped=2, files_removed=1, bytes_downloaded=1024)
        drive.duration_seconds = 1.2345
        if errors:
            drive.errors.append("some/file.pdf")
        summary.drive_stats = drive
        if photos:
            photo_stats = PhotoStats(photos_downloaded=3, photos_hardlinked=1, bytes_saved_by_hardlinks=99)
            photo_stats.albums_synced.append("Album 1")
            summary.photo_stats = photo_stats
        summary.sync_end_time = summary.sync_start_time + datetime.timedelta(seconds=4)
        return summary

    # --- the payload contract -------------------------------------------------

    def test_the_payload_shape_is_the_documented_one(self):
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            self.assertTrue(
                notify.post_event_to_webhook(self.CONFIG, "sync_started", "text", {"reason": "because"}),
            )
        self.assertEqual(post_mock.call_args.args, (self.URL,))
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(sorted(payload), ["data", "event", "message", "timestamp"])
        self.assertEqual(payload["event"], "sync_started")
        self.assertEqual(payload["message"], "text")
        self.assertEqual(payload["data"], {"reason": "because"})
        self.assertEqual(post_mock.call_args.kwargs["timeout"], notify.WEBHOOK_TIMEOUT_SECONDS)
        stamped = datetime.datetime.fromisoformat(payload["timestamp"])
        self.assertEqual(stamped.utcoffset(), datetime.timedelta(0))

    def test_an_event_without_data_still_carries_the_key(self):
        """A receiver indexing payload["data"] must not have to guard it."""
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            notify.post_event_to_webhook(self.CONFIG, "sync_started", "text")
        self.assertEqual(post_mock.call_args.kwargs["json"]["data"], {})

    def test_nothing_is_posted_without_a_url(self):
        with patch("src.notify.requests.post") as post_mock:
            self.assertFalse(notify.post_event_to_webhook({}, "sync_started", "text"))
            post_mock.assert_not_called()

    def test_configured_headers_are_sent(self):
        config = {"app": {"webhooks": {"url": self.URL, "headers": {"Authorization": "Bearer s3cret"}}}}
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            notify.post_event_to_webhook(config, "sync_started", "text")
        self.assertEqual(post_mock.call_args.kwargs["headers"], {"Authorization": "Bearer s3cret"})

    def test_no_headers_configured_sends_none(self):
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            notify.post_event_to_webhook(self.CONFIG, "sync_started", "text")
        self.assertIsNone(post_mock.call_args.kwargs["headers"])

    # --- failures stay quiet about the credentials ----------------------------

    def test_an_error_response_is_reported_without_the_url(self):
        with patch("src.notify.requests.post") as post_mock, patch("src.notify.LOGGER") as logger_mock:
            post_mock.return_value = Mock(ok=False, status_code=500)
            self.assertFalse(notify.post_event_to_webhook(self.CONFIG, "sync_failed", "text"))
        logged = " ".join(str(call) for call in logger_mock.warning.call_args_list)
        self.assertIn("sync_failed", logged)
        self.assertNotIn(self.URL, logged)

    def test_a_network_failure_leaks_neither_url_nor_headers(self):
        config = {"app": {"webhooks": {"url": self.URL, "headers": {"Authorization": "Bearer s3cret"}}}}
        boom = requests.exceptions.ConnectionError(f"Failed to establish a new connection to {self.URL}")
        with patch("src.notify.requests.post", side_effect=boom), patch("src.notify.LOGGER") as logger_mock:
            self.assertFalse(notify.post_event_to_webhook(config, "sync_summary", "text"))
        logged = " ".join(str(call) for call in logger_mock.warning.call_args_list)
        self.assertIn("ConnectionError", logged)
        self.assertNotIn(self.URL, logged)
        self.assertNotIn("s3cret", logged)

    # --- the events filter ----------------------------------------------------

    def test_an_absent_filter_sends_everything(self):
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            for event in notify.WEBHOOK_EVENTS:
                self.assertTrue(notify.post_event_to_webhook(self.CONFIG, event, "text"))
        self.assertEqual(post_mock.call_count, len(notify.WEBHOOK_EVENTS))

    def test_a_filter_sends_only_what_it_names(self):
        config = {"app": {"webhooks": {"url": self.URL, "events": ["sync_failed"]}}}
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            self.assertTrue(notify.post_event_to_webhook(config, "sync_failed", "text"))
            self.assertFalse(notify.post_event_to_webhook(config, "sync_succeeded", "text"))
        self.assertEqual(post_mock.call_count, 1)

    def test_an_empty_filter_sends_nothing(self):
        config = {"app": {"webhooks": {"url": self.URL, "events": []}}}
        with patch("src.notify.requests.post") as post_mock:
            self.assertFalse(notify.post_event_to_webhook(config, "sync_failed", "text"))
            post_mock.assert_not_called()

    def test_unknown_filter_entries_warn_once_naming_them(self):
        config = {"app": {"webhooks": {"url": self.URL, "events": ["sync_failed", "sync_finished", "oops"]}}}
        with patch("src.notify.LOGGER") as logger_mock:
            notify.warn_unknown_webhook_events(config)
        self.assertEqual(logger_mock.warning.call_count, 1)
        logged = str(logger_mock.warning.call_args)
        self.assertIn("oops", logged)
        self.assertIn("sync_finished", logged)
        self.assertNotIn("sync_failed,", logged.split("Known events")[0])

    def test_a_correct_filter_warns_about_nothing(self):
        config = {"app": {"webhooks": {"url": self.URL, "events": list(notify.WEBHOOK_EVENTS)}}}
        with patch("src.notify.LOGGER") as logger_mock:
            notify.warn_unknown_webhook_events(config)
            notify.warn_unknown_webhook_events({})
        logger_mock.warning.assert_not_called()

    # --- riding the existing dispatch ----------------------------------------

    def test_the_shared_24h_throttle_applies_to_a_webhook_only_install(self):
        """The whole point of being a transport in ``send()`` rather than a
        parallel path: with no other provider configured the webhook alone
        arms the window, and the second alert inside 24h is not sent."""
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            first = notify.send(self.CONFIG, "a@icloud.com")
            self.assertIsInstance(first, datetime.datetime)
            self.assertEqual(post_mock.call_count, 1)

            second = notify.send(self.CONFIG, "a@icloud.com", last_send=first)
            self.assertEqual(second, first)
            self.assertEqual(post_mock.call_count, 1)

    def test_an_auth_alert_names_its_event_and_carries_the_dashboard(self):
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            notify.send(
                self.CONFIG,
                "a@icloud.com",
                dashboard_url="https://icloud.test",
                event="password_missing",
            )
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(payload["event"], "password_missing")
        self.assertEqual(
            payload["data"],
            {"username": "a@icloud.com", "dashboard_url": "https://icloud.test"},
        )
        self.assertIn("icloud.test", payload["message"])

    def test_an_auth_alert_omits_an_unset_dashboard_instead_of_nulling_it(self):
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            notify.send(self.CONFIG, "a@icloud.com")
        self.assertEqual(post_mock.call_args.kwargs["json"]["data"], {"username": "a@icloud.com"})

    def test_a_trust_warning_carries_the_days_remaining(self):
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            notify.send_trust_expiring(self.CONFIG, "a@icloud.com", 3)
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(payload["event"], "trust_expiring")
        self.assertEqual(payload["data"], {"username": "a@icloud.com", "days_remaining": 3})

    def test_a_dry_run_sends_nothing_but_still_reports_sent(self):
        with patch("src.notify.requests.post") as post_mock:
            self.assertIsInstance(notify.send(self.CONFIG, "a@icloud.com", dry_run=True), datetime.datetime)
            self.assertIsInstance(
                notify.send_trust_expiring(self.CONFIG, "a@icloud.com", 3, dry_run=True),
                datetime.datetime,
            )
            post_mock.assert_not_called()

    def test_a_rejected_event_reports_failure(self):
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=False, status_code=503)
            self.assertIsNone(notify.send(self.CONFIG, "a@icloud.com"))

    # --- sync summary ---------------------------------------------------------

    def test_the_summary_payload_carries_the_stats_not_just_the_text(self):
        config = {
            "app": {
                "webhooks": {"url": self.URL},
                "notifications": {"sync_summary": {"enabled": True}},
            },
        }
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            self.assertTrue(notify.send_sync_summary(config, self._summary(photos=True)))
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(payload["event"], "sync_summary")
        self.assertEqual(payload["data"]["has_errors"], False)
        self.assertEqual(payload["data"]["duration_seconds"], 4.0)
        self.assertEqual(
            payload["data"]["drive"],
            {
                "files_downloaded": 5,
                "files_skipped": 2,
                "files_removed": 1,
                "bytes_downloaded": 1024,
                "duration_seconds": 1.234,
                "errors": 0,
            },
        )
        self.assertEqual(payload["data"]["photos"]["photos_downloaded"], 3)
        self.assertEqual(payload["data"]["photos"]["albums_synced"], ["Album 1"])

    def test_a_drive_only_summary_has_no_photos_key(self):
        data = notify.summary_event_data(self._summary(errors=True))
        self.assertNotIn("photos", data)
        self.assertEqual(data["drive"]["errors"], 1)
        self.assertTrue(data["has_errors"])

    def test_a_dry_run_summary_does_not_report_sent_without_a_url(self):
        """Without the URL check in the no-throttle sender, a dry run would
        log 'sync summary sent' on an install that has no webhook at all."""
        from src.notify import _send_webhook_no_throttle

        self.assertFalse(_send_webhook_no_throttle({}, "sync_summary", "text", {}, True))
        config = {"app": {"notifications": {"sync_summary": {"enabled": True}}}}
        self.assertFalse(notify.send_sync_summary(config, self._summary(), dry_run=True))

    def test_a_dry_run_summary_reports_sent_when_a_url_is_configured(self):
        from src.notify import _send_webhook_no_throttle

        with patch("src.notify.requests.post") as post_mock:
            self.assertTrue(_send_webhook_no_throttle(self.CONFIG, "sync_summary", "text", {}, True))
            post_mock.assert_not_called()

    # --- cycle boundaries reach both transports -------------------------------

    def test_a_boundary_pings_the_monitor_and_posts_the_event(self):
        config = {
            "app": {
                "webhooks": {
                    "url": self.URL,
                    "success": "https://hc-ping.com/uuid",
                },
            },
        }
        with (
            patch("src.notify.requests.get") as get_mock,
            patch("src.notify.requests.post") as post_mock,
        ):
            get_mock.return_value = Mock(ok=True)
            post_mock.return_value = Mock(ok=True)
            notify.send_cycle_event(config, "success", "done", {"reason": "none"})
        get_mock.assert_called_once_with("https://hc-ping.com/uuid", timeout=notify.WEBHOOK_TIMEOUT_SECONDS)
        self.assertEqual(post_mock.call_args.kwargs["json"]["event"], "sync_succeeded")

    def test_each_boundary_has_its_own_event_name(self):
        with patch("src.notify.requests.post") as post_mock:
            post_mock.return_value = Mock(ok=True)
            for boundary in ("start", "success", "failure"):
                notify.send_cycle_event(self.CONFIG, boundary, "text")
        self.assertEqual(
            [call.kwargs["json"]["event"] for call in post_mock.call_args_list],
            ["sync_started", "sync_succeeded", "sync_failed"],
        )


class TestWebhookQuietWhenUnconfigured(unittest.TestCase):
    """Most installs will never set a webhook. None of this may cost them a
    log line, which is why the URL is checked before the throttle."""

    def test_no_url_means_no_throttle_log(self):
        with patch("src.notify.LOGGER") as logger_mock:
            self.assertIsNone(
                notify.notify_webhook({}, "sync_failed", "text", last_send=datetime.datetime.now()),
            )
        logger_mock.info.assert_not_called()

    def test_a_configured_webhook_still_reports_the_throttle(self):
        config = {"app": {"webhooks": {"url": "https://receiver.test/hook"}}}
        with patch("src.notify.LOGGER") as logger_mock:
            last_send = datetime.datetime.now()
            self.assertEqual(
                notify.notify_webhook(config, "sync_failed", "text", last_send=last_send),
                last_send,
            )
        self.assertEqual(logger_mock.info.call_count, 1)
