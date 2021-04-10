import os
import unittest
import datetime

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



