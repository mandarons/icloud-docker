__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import unittest
import shutil

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
        self.assertIsNotNone(
            config_parser.read_config(config_path=constants.DEFAULT_CONFIG_FILE_PATH)
        )

    def test_read_config_invalids(self):
        # Invalid config path
        self.assertIsNone(config_parser.read_config(config_path="invalid/path"))
        # None config path
        self.assertIsNone(config_parser.read_config(config_path=None))

    def test_get_sync_interval_valids(self):
        # Given sync interval
        config = config_parser.read_config()
        self.assertEqual(
            config["app"]["sync_interval"],
            config_parser.get_sync_interval(config=config),
        )
        # Default sync interval
        del config["app"]["sync_interval"]
        self.assertEqual(
            constants.DEFAULT_SYNC_INTERVAL_SEC,
            config_parser.get_sync_interval(config=config),
        )

    def test_get_sync_interval_invalids(self):
        # None config
        self.assertEqual(
            constants.DEFAULT_SYNC_INTERVAL_SEC,
            config_parser.get_sync_interval(config=None),
        )

    def test_prepare_drive_destination_valids(self):
        config = config_parser.read_config()
        # Given destination
        actual = config_parser.prepare_drive_destination(config=config)
        self.assertEqual(
            os.path.abspath(
                os.path.join(config["app"]["root"], config["drive"]["destination"])
            ),
            actual,
        )
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))
        os.rmdir(actual)
        # Default destination
        del config["drive"]["destination"]
        actual = config_parser.prepare_drive_destination(config=config)
        self.assertEqual(
            os.path.abspath(
                os.path.join(
                    constants.DEFAULT_ROOT_DESTINATION,
                    constants.DEFAULT_DRIVE_DESTINATION,
                )
            ),
            actual,
        )
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))
        os.rmdir(actual)

    def test_prepare_drive_destination_invalids(self):
        # None config
        actual = config_parser.prepare_drive_destination(config=None)
        self.assertEqual(
            os.path.abspath(
                os.path.join(
                    constants.DEFAULT_ROOT_DESTINATION,
                    constants.DEFAULT_DRIVE_DESTINATION,
                )
            ),
            actual,
        )
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))
        os.rmdir(actual)

    def test_get_username_valids(self):
        config = config_parser.read_config()
        # Given username
        self.assertEqual(
            config["app"]["credentials"]["username"],
            config_parser.get_username(config=config),
        )

    def test_get_username_invalids(self):
        config = config_parser.read_config()
        # None config
        self.assertIsNone(config_parser.get_username(config=None))
        # Empty username
        config["app"]["credentials"]["username"] = ""
        self.assertIsNone(config_parser.get_username(config=config))

    def test_get_remove_obsolete_valids(self):
        config = config_parser.read_config()
        config["drive"]["remove_obsolete"] = True
        self.assertTrue(config_parser.get_drive_remove_obsolete(config=config))
        del config["drive"]["remove_obsolete"]
        self.assertFalse(config_parser.get_drive_remove_obsolete(config=config))

    def test_get_remove_obsolete_invalids(self):
        self.assertFalse(config_parser.get_drive_remove_obsolete(config=None))

    def test_get_verbose_valids(self):
        config = config_parser.read_config()
        self.assertEqual(
            config["app"]["verbose"], config_parser.get_verbose(config=config)
        )
        config["app"]["verbose"] = True
        self.assertTrue(config_parser.get_verbose(config=config))

    def test_get_verbose_invalids(self):
        config = config_parser.read_config()
        config["app"]["verbose"] = None
        self.assertFalse(config_parser.get_verbose(config=config))
        del config["app"]["verbose"]
        self.assertFalse(config_parser.get_verbose(config=config))
        del config["app"]
        self.assertFalse(config_parser.get_verbose(config=config))

    def test_get_smtp_no_tls(self):
        config = {"app": {"smtp": {"no_tls": True}}}
        self.assertTrue(config_parser.get_smtp_no_tls(config=config))
        config = {"app": {"smtp": {"no_tls": False}}}
        self.assertFalse(config_parser.get_smtp_no_tls(config=config))
        config = {"app": {"smtp": {}}}
        self.assertFalse(config_parser.get_smtp_no_tls(config=config))

    def test_get_smtp_email_valids(self):
        # Given email
        config = {"app": {"smtp": {"email": "user@test.com"}}}
        self.assertEqual(
            config["app"]["smtp"]["email"], config_parser.get_smtp_email(config=config)
        )

    def test_smtp_email_invalids(self):
        self.assertIsNone(config_parser.get_smtp_email(config=None))

    def test_get_smtp_host_valids(self):
        # Given host
        config = {"app": {"smtp": {"host": "smtp.test.com"}}}
        self.assertEqual(
            config["app"]["smtp"]["host"], config_parser.get_smtp_host(config=config)
        )

    def test_smtp_host_invalids(self):
        self.assertIsNone(config_parser.get_smtp_host(config=None))

    def test_get_smtp_port_valids(self):
        # Given port
        config = {"app": {"smtp": {"port": 587}}}
        self.assertEqual(
            config["app"]["smtp"]["port"], config_parser.get_smtp_port(config=config)
        )

    def test_smtp_port_invalids(self):
        self.assertIsNone(config_parser.get_smtp_port(config=None))

    def test_get_smtp_password_valids(self):
        # Given password
        config = {"app": {"smtp": {"password": "password"}}}
        self.assertEqual(
            config["app"]["smtp"]["password"],
            config_parser.get_smtp_password(config=config),
        )

    def test_smtp_password_invalids(self):
        self.assertIsNone(config_parser.get_smtp_password(config=None))

    def test_prepare_photos_destination_valids(self):
        config = config_parser.read_config()
        # Given destination
        actual = config_parser.prepare_photos_destination(config=config)
        self.assertEqual(
            os.path.abspath(
                os.path.join(config["app"]["root"], config["photos"]["destination"])
            ),
            actual,
        )
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))
        os.rmdir(actual)
        # Default destination
        del config["photos"]["destination"]
        actual = config_parser.prepare_photos_destination(config=config)
        self.assertEqual(
            os.path.abspath(
                os.path.join(
                    constants.DEFAULT_ROOT_DESTINATION,
                    constants.DEFAULT_PHOTOS_DESTINATION,
                )
            ),
            actual,
        )
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))
        shutil.rmtree(actual)

    def test_prepare_photos_destination_invalids(self):
        # None config
        actual = config_parser.prepare_photos_destination(config=None)
        self.assertEqual(
            os.path.abspath(
                os.path.join(
                    constants.DEFAULT_ROOT_DESTINATION,
                    constants.DEFAULT_PHOTOS_DESTINATION,
                )
            ),
            actual,
        )
        self.assertTrue(os.path.exists(actual))
        self.assertTrue(os.path.isdir(actual))
        shutil.rmtree(actual)

    def test_get_photos_remove_obsolete_valids(self):
        config = config_parser.read_config()
        config["photos"]["remove_obsolete"] = True
        self.assertTrue(config_parser.get_photos_remove_obsolete(config=config))
        del config["photos"]["remove_obsolete"]
        self.assertFalse(config_parser.get_photos_remove_obsolete(config=config))

    def test_get_photos_remove_obsolete_invalids(self):
        self.assertFalse(config_parser.get_photos_remove_obsolete(config=None))

    def test_get_photos_filters_valids(self):
        config = config_parser.read_config()
        expected_albums = ["Screenshots", "Selfies"]
        expected_file_sizes = ["original", "medium", "thumb"]
        config["photos"]["filters"]["albums"] = expected_albums
        config["photos"]["filters"]["file_sizes"] = expected_file_sizes
        actual = config_parser.get_photos_filters(config=config)
        self.assertIsNotNone(actual)
        self.assertListEqual(actual["albums"], expected_albums)
        self.assertListEqual(actual["file_sizes"], expected_file_sizes)

    def test_get_photos_filters_invalids(self):
        config = config_parser.read_config()
        del config["photos"]["filters"]
        actual = config_parser.get_photos_filters(config=config)
        self.assertIsNone(actual["albums"])
        self.assertEqual(actual["file_sizes"][0], "original")
        config["photos"] = {"filters": {"file_sizes": ["invalid"]}}
        actual = config_parser.get_photos_filters(config=config)
        self.assertEqual(actual["file_sizes"][0], "original")
        del config["photos"]["filters"]["file_sizes"]
        actual = config_parser.get_photos_filters(config=config)
        self.assertEqual(actual["file_sizes"][0], "original")
