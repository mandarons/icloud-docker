"""Test for notify.py file."""

import datetime
import unittest
from unittest.mock import patch

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
        self.assertIn(self.config["app"]["smtp"]["email"], msg.sender)
        self.assertIn(subject, msg.subject)
        self.assertIn(
            message,
            msg.body,
        )
        self.assertIsInstance(msg, Message)

    def test_send(self):
        """Test for email send."""
        username = "username@icloud.com"
        with patch("smtplib.SMTP") as smtp, \
             patch("src.notify.post_message_to_telegram"), \
             patch("src.notify.post_message_to_discord"), \
             patch("src.notify.post_message_to_pushover"):
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
                "Subject: icloud-docker: Two step authentication is required",
                instance.sendmail.mock_calls[0][2]["msg"],
            )

    def test_send_with_username(self):
        """Test for email send."""
        username = "username@icloud.com"
        with patch("smtplib.SMTP") as smtp, \
             patch("src.notify.post_message_to_telegram"), \
             patch("src.notify.post_message_to_discord"), \
             patch("src.notify.post_message_to_pushover"):
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
                "Subject: icloud-docker: Two step authentication is required",
                instance.sendmail.mock_calls[0][2]["msg"],
            )
            self.assertNotIn("--region=", instance.sendmail.mock_calls[0][2]["msg"])

    def test_send_with_region(self):
        """Test for email send with region."""
        username = "username@icloud.com"
        with patch("smtplib.SMTP") as smtp, \
             patch("src.notify.post_message_to_telegram"), \
             patch("src.notify.post_message_to_discord"), \
             patch("src.notify.post_message_to_pushover"):
            notify.send(self.config, username, region="some_region")

            instance = smtp.return_value
            self.assertIn("--region=some_region", instance.sendmail.mock_calls[0][2]["msg"])

    def test_send_fail(self):
        """Test for failed send."""
        username = "username@icloud.com"
        with patch("smtplib.SMTP") as smtp, \
             patch("src.notify.post_message_to_telegram") as telegram_mock, \
             patch("src.notify.post_message_to_discord") as discord_mock, \
             patch("src.notify.post_message_to_pushover") as pushover_mock:
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
            drive_stats=DriveStats(files_downloaded=15, files_skipped=234, bytes_downloaded=2415919104, duration_seconds=272),
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
            drive_stats=DriveStats(files_downloaded=3, errors=["/path/file1.txt (timeout)", "/path/file2.pdf (API error)"]),
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
            post_message_to_pushover("pushover_api_token", "pushover_user_key", "message")

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
            post_message_to_pushover("pushover_api_token", "pushover_user_key", "message")

            # Verify that post is called with the correct arguments
            post_mock.assert_called_once_with(
                "https://api.pushover.net/1/messages.json",
                data={"token": "pushover_api_token", "user": "pushover_user_key", "message": "message"},
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
