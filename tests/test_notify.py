import os
import unittest
import datetime

from unittest.mock import patch, call
from mailer import Message
from src import config_parser
from src import notify

class TestNotify(unittest.TestCase):
    def setUp(self) -> None:
        self.config={'smtp':{
            'email':    'user@test.com',
            'host':     'smtp.test.com',
            'port':     '587',
            'password': 'password',
        }}

    def tearDown(self) -> None:
        pass

    def test_throttling(self):
        not_24_hours = datetime.datetime.now()
        # if less than 24 hours has passed since last send, then the same
        # datetime object is returned
        self.assertEqual(not_24_hours, notify.send(self.config, not_24_hours, dry_run=True))

    def test_no_smtp_config(self):
        # None is returned if email didn't send because of missing config
        self.assertIsNone(notify.send({}, None, dry_run=True))

    def test_dry_run_send(self):
        # send returns the datetime of the request
        self.assertIsInstance(notify.send(self.config, None, dry_run=True), datetime.datetime)

    def test_build_message(self):
        msg = notify.build_message(self.config['smtp']['email'])
        self.assertEqual(msg.To, self.config['smtp']['email'])
        self.assertIn(self.config['smtp']['email'], msg.From)
        self.assertIn('icloud-drive-docker: Two step authentication required', msg.Subject)
        self.assertIn('Two-step authentication for iCloud Drive (Docker) is required.', msg.Body)
        self.assertIsInstance(msg, Message)

    def test_send(self):
        with patch("smtplib.SMTP") as smtp:
            notify.send(self.config)

            instance = smtp.return_value

            # verify that sendmail() was called
            self.assertTrue(instance.sendmail.called)
            self.assertEqual(instance.sendmail.call_count, 1)

            # verify that the correct email is being sent to sendmail()
            self.assertEqual(config_parser.get_smtp_email(config=self.config), instance.sendmail.mock_calls[0][1][1])
            # verify that the message was passed to sendmail()
            self.assertIn('Subject: icloud-drive-docker: Two step authentication required', instance.sendmail.mock_calls[0][1][2])

    def test_send_fail(self):
        with patch("smtplib.SMTP") as smtp:
            smtp.side_effect = Exception

            # Verify that a failure doesn't return a send_on timestamp
            sent_on = notify.send(self.config)
            self.assertEquals(None, sent_on)

