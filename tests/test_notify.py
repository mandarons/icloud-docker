"""Test for notify.py file."""

import datetime
import unittest
from unittest.mock import patch

from src import config_parser, notify
from src.email_message import EmailMessage as Message
from src.notify import (
    notify_discord,
    notify_telegram,
    post_message_to_discord,
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
        with patch("smtplib.SMTP") as smtp:
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
        with patch("smtplib.SMTP") as smtp:
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
        with patch("smtplib.SMTP") as smtp:
            notify.send(self.config, username, region="some_region")

            instance = smtp.return_value
            self.assertIn("--region=some_region", instance.sendmail.mock_calls[0][2]["msg"])

    def test_send_fail(self):
        """Test for failed send."""
        username = "username@icloud.com"
        with patch("smtplib.SMTP") as smtp:
            smtp.side_effect = Exception

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
