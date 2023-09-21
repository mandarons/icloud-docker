"""Test for notify.py file."""
import datetime
import unittest
from unittest.mock import patch

from src import config_parser, notify
from src.email_message import EmailMessage as Message


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
                }
            }
        }

    def test_throttling(self):
        """Test for throttled notification."""
        not_24_hours = datetime.datetime.now()
        # if less than 24 hours has passed since last send, then the same
        # datetime object is returned
        self.assertEqual(
            not_24_hours, notify.send(self.config, not_24_hours, dry_run=True)
        )

    def test_no_smtp_config(self):
        """Test for None is returned if email didn't send because of missing config."""
        self.assertIsNone(notify.send({}, None, dry_run=True))

    def test_dry_run_send(self):
        """Test for send returns the datetime of the request."""
        self.assertIsInstance(
            notify.send(self.config, None, dry_run=True), datetime.datetime
        )

    def test_build_message(self):
        """Test for building a valid email."""
        msg = notify.build_message(
            email=self.config["app"]["smtp"]["email"],
            to_email=self.config["app"]["smtp"]["to"],
        )
        self.assertEqual(msg.to, self.config["app"]["smtp"]["to"])
        self.assertIn(self.config["app"]["smtp"]["email"], msg.sender)
        self.assertIn("icloud-docker: Two step authentication required", msg.subject)
        self.assertIn(
            "Two-step authentication for iCloud Drive, Photos (Docker) is required.",
            msg.body,
        )
        self.assertIsInstance(msg, Message)

    def test_send(self):
        """Test for email send."""
        with patch("smtplib.SMTP") as smtp:
            notify.send(self.config)

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
                "Subject: icloud-docker: Two step authentication required",
                instance.sendmail.mock_calls[0][2]["msg"],
            )

    def test_send_with_username(self):
        """Test for email send."""
        with patch("smtplib.SMTP") as smtp:
            self.config["app"]["smtp"]["username"] = "smtp-username"
            notify.send(self.config)

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
                "Subject: icloud-docker: Two step authentication required",
                instance.sendmail.mock_calls[0][2]["msg"],
            )

    def test_send_fail(self):
        """Test for failed send."""
        with patch("smtplib.SMTP") as smtp:
            smtp.side_effect = Exception

            # Verify that a failure doesn't return a send_on timestamp
            sent_on = notify.send(self.config)
            self.assertEqual(None, sent_on)
