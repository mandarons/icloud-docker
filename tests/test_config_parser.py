__author__ = 'Mandar Patil (mandarons@pm.me)'

import os
import unittest

from src import config_parser, constants


class TestConfigParser(unittest.TestCase):

    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass

    def test_read_config_valids(self):
        # Default config path
        self.assertIsNotNone(config_parser.read_config())
        # Overridden config path
        self.assertIsNotNone(config_parser.read_config(config_path=constants.DEFAULT_CONFIG_FILE_PATH))

    def test_read_config_invalids(self):
        # Invalid config path
        self.assertIsNone(config_parser.read_config(config_path='invalid/path'))
        # None config path
        self.assertIsNone(config_parser.read_config(config_path=None))

    def test_get_sync_interval_valids(self):
        # Given sync interval
        config = config_parser.read_config()
        self.assertEqual(config['settings']['sync_interval'], config_parser.get_sync_interval(config=config))
        # Default sync interval
        del config['settings']['sync_interval']
        self.assertEqual(constants.DEFAULT_SYNC_INTERVAL_SEC, config_parser.get_sync_interval(config=config))

    def test_get_sync_interval_invalids(self):
        # None config
        self.assertEqual(constants.DEFAULT_SYNC_INTERVAL_SEC, config_parser.get_sync_interval(config=None))

    def test_prepare_destination_valids(self):
        config = config_parser.read_config()
        # Given destination
        actual = config_parser.prepare_destination(config=config)
        self.assertEqual(os.path.abspath(config['settings']['destination']), actual)
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))
        os.rmdir(actual)
        # Default destination
        del config['settings']['destination']
        actual = config_parser.prepare_destination(config=config)
        self.assertEqual(os.path.abspath(constants.DEFAULT_DRIVE_DESTINATION), actual)
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))
        os.rmdir(actual)

    def test_prepare_destination_invalids(self):
        # None config
        actual = config_parser.prepare_destination(config=None)
        self.assertEqual(os.path.abspath(constants.DEFAULT_DRIVE_DESTINATION), actual)
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))
        os.rmdir(actual)

    def test_get_username_valids(self):
        config = config_parser.read_config()
        # Given username
        self.assertEqual(config['credentials']['username'], config_parser.get_username(config=config))

    def test_get_username_invalids(self):
        config = config_parser.read_config()
        # None config
        self.assertIsNone(config_parser.get_username(config=None))
        # Empty username
        config['credentials']['username'] = ''
        self.assertIsNone(config_parser.get_username(config=config))

    def test_get_remove_obsolete_valids(self):
        config = config_parser.read_config()
        config['settings']['remove_obsolete'] = True
        self.assertTrue(config_parser.get_remove_obsolete(config=config))
        del config['settings']['remove_obsolete']
        self.assertFalse(config_parser.get_remove_obsolete(config=config))

    def test_get_remove_obsolete_invalids(self):
        self.assertFalse(config_parser.get_remove_obsolete(config=None))

    def test_get_verbose_valids(self):
        config = config_parser.read_config()
        self.assertEqual(config['settings']['verbose'],config_parser.get_verbose(config=config))
        config['settings']['verbose'] = True
        self.assertTrue(config_parser.get_verbose(config=config))

    def test_get_verbose_invalids(self):
        config = config_parser.read_config()
        config['settings']['verbose'] = None
        self.assertFalse(config_parser.get_verbose(config=config))
        del config['settings']['verbose']
        self.assertFalse(config_parser.get_verbose(config=config))
        del config['settings']
        self.assertFalse(config_parser.get_verbose(config=config))

    def test_get_smtp_no_tls(self):
        config = {'smtp':{'no_tls':True}}
        self.assertTrue(config_parser.get_smtp_no_tls(config=config))
        config = {'smtp':{'no_tls':False}}
        self.assertFalse(config_parser.get_smtp_no_tls(config=config))
        del config['smtp']['no_tls']
        self.assertFalse(config_parser.get_smtp_no_tls(config=config))

    def test_get_smtp_email_valids(self):
        # Given email
        config = {'smtp':{'email':'user@test.com'}}
        self.assertEqual(config['smtp']['email'], config_parser.get_smtp_email(config=config))

    def test_smtp_email_invalids(self):
        self.assertIsNone(config_parser.get_smtp_email(config=None))

    def test_get_smtp_host_valids(self):
        # Given host
        config = {'smtp':{'host':'smtp.test.com'}}
        self.assertEqual(config['smtp']['host'], config_parser.get_smtp_host(config=config))

    def test_smtp_host_invalids(self):
        self.assertIsNone(config_parser.get_smtp_host(config=None))

    def test_get_smtp_port_valids(self):
        # Given port
        config = {'smtp':{'port':'587'}}
        self.assertEqual(config['smtp']['port'], config_parser.get_smtp_port(config=config))

    def test_smtp_port_invalids(self):
        self.assertIsNone(config_parser.get_smtp_port(config=None))

    def test_get_smtp_password_valids(self):
        # Given password
        config = {'smtp':{'password':'password'}}
        self.assertEqual(config['smtp']['password'], config_parser.get_smtp_password(config=config))

    def test_smtp_password_invalids(self):
        self.assertIsNone(config_parser.get_smtp_password(config=None))
