"""Tests for usage.py file."""

import datetime
import os
import unittest
import uuid
from unittest.mock import patch

import tests
from src import read_config, usage


class TestUsage(unittest.TestCase):
    """Tests for usage."""

    def setUp(self) -> None:
        """Set up test."""
        self.new_installation_data = dict(usage.NEW_INSTALLATION_DATA)
        self.config = read_config(config_path=tests.CONFIG_PATH)
        file_path = usage.init_cache(config=self.config)
        if os.path.isfile(file_path):
            os.remove(file_path)
        return super().setUp()

    def tearDown(self) -> None:
        """Tear down test."""
        file_path = usage.init_cache(config=self.config)
        if os.path.isfile(file_path):
            os.remove(file_path)
        return super().tearDown()

    def test_init_cache_valid(self):
        """Test for valid cache."""
        result = usage.init_cache(config=self.config)
        self.assertIsNotNone(result)
        self.assertTrue(len(result) > 0)

    def test_load_cache_empty(self):
        """Test for empty cache load."""
        file_path = usage.init_cache(config=self.config)
        actual = usage.load_cache(file_path=file_path)
        self.assertIsNotNone(actual)
        self.assertDictEqual(actual, {})
        self.assertTrue(os.path.isfile(file_path))

    def test_load_cache_non_empty(self):
        """Test for non-empty cache load."""
        file_path = usage.init_cache(config=self.config)
        data = {"id": str(uuid.uuid4())}
        usage.save_cache(file_path=file_path, data=data)
        actual = usage.load_cache(file_path=file_path)
        self.assertIn("id", actual)
        self.assertDictEqual(actual, data)

    def test_save_cache(self):
        """Test for saving the data to cache file."""
        file_path = usage.init_cache(config=self.config)
        data = {"id": str(uuid.uuid4())}
        actual = usage.save_cache(file_path=file_path, data=data)
        self.assertTrue(actual)
        actual = usage.load_cache(file_path=file_path)
        self.assertDictEqual(data, actual)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_post_new_installation_valid(self, mock_post):
        """Test for posting new installation."""
        actual = usage.post_new_installation(data=dict(self.new_installation_data))
        self.assertIsNotNone(actual)
        self.assertTrue(len(actual) > 0)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_post_new_installation_error(self, mock_post):
        """Test for post failure."""
        actual = usage.post_new_installation(data=dict(self.new_installation_data), endpoint="Invalid")
        self.assertIsNone(actual)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_record_new_installation_valid(self, mock_post):
        """Test for valid new installation."""
        actual = usage.record_new_installation()
        self.assertIsNotNone(actual)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_record_new_installation_previous_id(self, mock_post):
        """Test for upgrade existing installation."""
        previous_id = str(uuid.uuid4())
        actual = usage.record_new_installation(previous_id=previous_id)
        self.assertIsNotNone(actual)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_install_fresh(self, mock_post):
        """Test for fresh installation."""
        file_path = usage.init_cache(config=self.config)
        cached_data = usage.load_cache(file_path=file_path)
        actual = usage.install(cached_data=cached_data)
        self.assertTrue(actual is not False)
        self.assertIn("id", actual)
        self.assertIn("app_version", actual)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_install_upgrade(self, mock_post):
        """Test for ugprade."""
        file_path = usage.init_cache(config=self.config)
        cached_data = usage.load_cache(file_path=file_path)
        fresh = usage.install(cached_data=cached_data)
        actual = usage.install(cached_data=dict(fresh))
        self.assertTrue(actual is not False)
        self.assertIn("id", actual)
        self.assertIn("app_version", actual)
        self.assertTrue(actual["id"] is not fresh["id"])

    @patch("requests.post", side_effect=Exception("Error occurred."))
    def test_install_post_exception(self, mock_post):
        """Test for fresh installation handle post exception."""
        file_path = usage.init_cache(config=self.config)
        cached_data = usage.load_cache(file_path=file_path)
        actual = usage.install(cached_data=cached_data)
        self.assertFalse(actual)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_new_heartbeat_valid(self, mock_post):
        """Test new heartbeat to server."""
        file_path = usage.init_cache(config=self.config)
        cached_data = usage.load_cache(file_path=file_path)
        fresh = usage.install(cached_data=cached_data)
        actual = usage.post_new_heartbeat(data={"installationId": fresh["id"], "data": None})
        self.assertTrue(actual)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_new_heartbeat_invalid(self, mock_post):
        """Test new invalid heartbeat to server."""
        file_path = usage.init_cache(config=self.config)
        cached_data = usage.load_cache(file_path=file_path)
        fresh = usage.install(cached_data=cached_data)
        actual = usage.post_new_heartbeat(data={"installationId": fresh["id"], "data": None}, endpoint="invalid")
        self.assertFalse(actual)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_new_heartbeat_post_exception(self, mock_post):
        """Test new heartbeat handle post exception."""
        file_path = usage.init_cache(config=self.config)
        cached_data = usage.load_cache(file_path=file_path)
        fresh = usage.install(cached_data=cached_data)
        mock_post.side_effect = Exception("Error occurred.")
        actual = usage.post_new_heartbeat(data={"installationId": fresh["id"], "data": None})
        self.assertFalse(actual)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_alive_valid(self, mock_post):
        """Test alive functionality."""
        # Test first run - install
        actual = usage.alive(config=self.config)
        self.assertTrue(actual)
        # Test second run - no install but heartbeat
        actual = usage.alive(config=self.config)
        self.assertTrue(actual)
        # Test third run - no install, no heartbeat
        actual = usage.alive(config=self.config)
        self.assertFalse(actual)

        # Test heartbeat 24 hours ago
        mock_now = datetime.datetime.now() + datetime.timedelta(hours=25)
        with patch("src.usage.current_time") as mock_datetime_now:
            mock_datetime_now.return_value = mock_now
            actual = usage.alive(config=self.config)
            self.assertTrue(actual)
