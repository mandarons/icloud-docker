"""Tests for usage.py file."""

import datetime
import os
import unittest
import uuid
from unittest.mock import MagicMock, patch

import requests

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
        # Test third run - no install, no heartbeat (same day)
        actual = usage.alive(config=self.config)
        self.assertFalse(actual)

        # Test heartbeat on next UTC day (even if less than 24 hours)
        mock_now = datetime.datetime.utcnow() + datetime.timedelta(days=1)
        with patch("src.usage.current_time") as mock_datetime_now:
            mock_datetime_now.return_value = mock_now
            actual = usage.alive(config=self.config)
            self.assertTrue(actual)

    def test_validate_cache_data_invalid_dict(self):
        """Test cache validation with invalid data types."""
        # Test non-dict input
        self.assertFalse(usage.validate_cache_data("not a dict"))
        self.assertFalse(usage.validate_cache_data([]))
        self.assertFalse(usage.validate_cache_data(None))

    def test_validate_cache_data_invalid_id(self):
        """Test cache validation with invalid ID."""
        # Test invalid ID type
        self.assertFalse(usage.validate_cache_data({"id": 123}))
        self.assertFalse(usage.validate_cache_data({"id": None}))

    def test_validate_cache_data_invalid_app_version(self):
        """Test cache validation with invalid app version."""
        # Test invalid app_version type
        self.assertFalse(usage.validate_cache_data({"app_version": 123}))
        self.assertFalse(usage.validate_cache_data({"app_version": None}))

    def test_validate_cache_data_invalid_timestamp(self):
        """Test cache validation with invalid timestamp."""
        # Test invalid timestamp format
        self.assertFalse(usage.validate_cache_data({"heartbeat_timestamp": "invalid"}))
        self.assertFalse(usage.validate_cache_data({"heartbeat_timestamp": 123}))
        self.assertFalse(usage.validate_cache_data({"heartbeat_timestamp": None}))

    def test_validate_cache_data_valid(self):
        """Test cache validation with valid data."""
        # Test empty dict (valid)
        self.assertTrue(usage.validate_cache_data({}))

        # Test valid complete data
        valid_data = {
            "id": str(uuid.uuid4()),
            "app_version": "1.0.0",
            "heartbeat_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        }
        self.assertTrue(usage.validate_cache_data(valid_data))

    def test_load_cache_corrupted_validation(self):
        """Test loading corrupted cache that fails validation."""
        file_path = usage.init_cache(config=self.config)

        # Write invalid data directly to file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write('{"id": 123, "app_version": null}')

        # Load should detect invalid data and create new cache
        data = usage.load_cache(file_path)
        self.assertEqual(data, {})

    def test_load_cache_json_decode_error(self):
        """Test loading cache with JSON decode error."""
        file_path = usage.init_cache(config=self.config)

        # Write invalid JSON to file
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("invalid json")

        # Load should handle JSON error and create new cache
        data = usage.load_cache(file_path)
        self.assertEqual(data, {})

    @patch("os.rename")
    def test_save_cache_os_error(self, mock_rename):
        """Test save cache with OS error."""
        mock_rename.side_effect = OSError("Permission denied")

        file_path = usage.init_cache(config=self.config)
        result = usage.save_cache(file_path, {"test": "data"})
        self.assertFalse(result)

    @patch("tempfile.NamedTemporaryFile")
    def test_save_cache_temp_file_error(self, mock_temp):
        """Test save cache with temporary file error."""
        mock_temp.side_effect = OSError("Cannot create temp file")

        file_path = usage.init_cache(config=self.config)
        result = usage.save_cache(file_path, {"test": "data"})
        self.assertFalse(result)

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_usage_tracking_disabled(self, mock_post):
        """Test that usage tracking can be disabled."""
        # Modify config to disable usage tracking
        config_with_disabled = dict(self.config)
        config_with_disabled["app"] = {"usage_tracking": {"enabled": False}}

        # Should return True but not actually send any requests
        result = usage.alive(config=config_with_disabled)
        self.assertTrue(result)

        # No HTTP requests should have been made
        mock_post.assert_not_called()

    @patch("requests.post", side_effect=tests.mocked_usage_post)
    def test_alive_with_usage_data(self, mock_post):
        """Test alive function with usage data."""
        test_data = {
            "sync_duration": 123.45,
            "has_errors": False,
            "files_count": 10,
        }

        # First call should install
        result = usage.alive(config=self.config, data=test_data)
        self.assertTrue(result)

        # Second call should send heartbeat with data
        result = usage.alive(config=self.config, data=test_data)
        self.assertTrue(result)

    def test_heartbeat_invalid_timestamp(self):
        """Test heartbeat with invalid timestamp in cache."""
        # Create cache with invalid timestamp
        cached_data = {
            "id": str(uuid.uuid4()),
            "app_version": usage.APP_VERSION,
            "heartbeat_timestamp": "invalid-timestamp",
        }

        with patch("src.usage.send_heartbeat") as mock_send:
            mock_send.return_value = True
            result = usage.heartbeat(cached_data, None)
            # Should treat as first heartbeat due to invalid timestamp
            self.assertIsNotNone(result)
            mock_send.assert_called_once()

    @patch("os.unlink")
    @patch("tempfile.NamedTemporaryFile")
    def test_save_cache_cleanup_temp_file(self, mock_temp, mock_unlink):
        """Test save cache temp file cleanup on error."""
        # Mock NamedTemporaryFile to succeed but os.rename to fail
        mock_temp_file = mock_temp.return_value.__enter__.return_value
        mock_temp_file.name = "/tmp/test_file.tmp"

        with patch("os.rename", side_effect=OSError("Rename failed")):
            file_path = usage.init_cache(config=self.config)
            result = usage.save_cache(file_path, {"test": "data"})
            self.assertFalse(result)
            mock_unlink.assert_called_once_with("/tmp/test_file.tmp")

    @patch("os.unlink", side_effect=OSError("Cannot delete temp file"))
    @patch("tempfile.NamedTemporaryFile")
    def test_save_cache_cleanup_temp_file_fails(self, mock_temp, mock_unlink):
        """Test save cache temp file cleanup when unlink also fails."""
        # Mock NamedTemporaryFile to succeed but os.rename to fail
        mock_temp_file = mock_temp.return_value.__enter__.return_value
        mock_temp_file.name = "/tmp/test_file.tmp"

        with patch("os.rename", side_effect=OSError("Rename failed")):
            file_path = usage.init_cache(config=self.config)
            result = usage.save_cache(file_path, {"test": "data"})
            self.assertFalse(result)
            # This should test the except OSError: pass block
            mock_unlink.assert_called_once_with("/tmp/test_file.tmp")

    @patch("src.usage.send_heartbeat")
    def test_heartbeat_send_failure(self, mock_send):
        """Test heartbeat when send_heartbeat fails."""
        mock_send.return_value = False

        # Test with no previous heartbeat (first heartbeat failure)
        cached_data = {"id": str(uuid.uuid4())}
        result = usage.heartbeat(cached_data, None)
        self.assertIsNone(result)

        # Test with old heartbeat (24+ hours ago, but send fails)
        past_time = (datetime.datetime.now() - datetime.timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S.%f")
        cached_data["heartbeat_timestamp"] = past_time
        result = usage.heartbeat(cached_data, None)
        self.assertIsNone(result)

    @patch("requests.post", side_effect=Exception("Network error"))
    def test_alive_installation_failure(self, mock_post):
        """Test alive when installation fails."""
        result = usage.alive(config=self.config)
        self.assertFalse(result)

    @patch("src.usage.send_heartbeat")
    def test_heartbeat_same_utc_day(self, mock_send):
        """Test heartbeat throttled when same UTC day."""
        mock_send.return_value = True

        # Create a timestamp for earlier today
        now = datetime.datetime.utcnow()
        earlier_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        cached_data = {
            "id": str(uuid.uuid4()),
            "heartbeat_timestamp": earlier_today.strftime("%Y-%m-%d %H:%M:%S.%f"),
        }

        # Mock current time to be later same day
        later_today = earlier_today.replace(hour=23, minute=59, second=59)
        with patch("src.usage.current_time") as mock_time:
            mock_time.return_value = later_today
            result = usage.heartbeat(cached_data, None)
            # Should be throttled even though almost 24 hours
            self.assertIsNone(result)
            mock_send.assert_not_called()

    @patch("src.usage.send_heartbeat")
    def test_heartbeat_different_utc_day(self, mock_send):
        """Test heartbeat sent when different UTC day."""
        mock_send.return_value = True

        # Create a timestamp for yesterday
        today = datetime.datetime.utcnow()
        yesterday = today - datetime.timedelta(days=1)

        cached_data = {
            "id": str(uuid.uuid4()),
            "heartbeat_timestamp": yesterday.strftime("%Y-%m-%d %H:%M:%S.%f"),
        }

        # Mock current time to be today
        with patch("src.usage.current_time") as mock_time:
            mock_time.return_value = today
            result = usage.heartbeat(cached_data, None)
            # Should send heartbeat
            self.assertIsNotNone(result)
            self.assertEqual(result["heartbeat_timestamp"], str(today))
            mock_send.assert_called_once()

    @patch("src.usage.send_heartbeat")
    def test_heartbeat_utc_midnight_boundary(self, mock_send):
        """Test heartbeat at UTC midnight boundary."""
        mock_send.return_value = True

        # Create timestamp at 23:59:59 yesterday
        today = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_night = today - datetime.timedelta(seconds=1)

        cached_data = {
            "id": str(uuid.uuid4()),
            "heartbeat_timestamp": yesterday_night.strftime("%Y-%m-%d %H:%M:%S.%f"),
        }

        # Mock current time to be 00:00:01 today (1 second after midnight)
        today_morning = today + datetime.timedelta(seconds=1)
        with patch("src.usage.current_time") as mock_time:
            mock_time.return_value = today_morning
            result = usage.heartbeat(cached_data, None)
            # Should send heartbeat even though only 2 seconds apart
            self.assertIsNotNone(result)
            mock_send.assert_called_once()

    @patch("src.usage.send_heartbeat")
    def test_heartbeat_uses_utc_not_local(self, mock_send):
        """Test that heartbeat uses UTC time, not local time."""
        mock_send.return_value = True

        # Create a timestamp using UTC
        utc_yesterday = datetime.datetime.utcnow() - datetime.timedelta(days=1)

        cached_data = {
            "id": str(uuid.uuid4()),
            "heartbeat_timestamp": utc_yesterday.strftime("%Y-%m-%d %H:%M:%S.%f"),
        }

        # The heartbeat should use UTC time internally
        result = usage.heartbeat(cached_data, None)

        # Should send heartbeat because it's a different UTC day
        self.assertIsNotNone(result)

        # Verify the timestamp is in UTC format and can be parsed
        new_timestamp = result["heartbeat_timestamp"]
        parsed = datetime.datetime.strptime(new_timestamp, "%Y-%m-%d %H:%M:%S.%f")

        # The date should be today in UTC, not local
        utc_today = datetime.datetime.utcnow().date()
        self.assertEqual(parsed.date(), utc_today)

    def test_current_time_returns_utc(self):
        """Test that current_time returns UTC time."""
        result = usage.current_time()

        # Should be close to utcnow, not now
        utc_now = datetime.datetime.utcnow()

        # Result should be within 1 second of UTC now
        self.assertLess(abs((result - utc_now).total_seconds()), 1)

        # In most timezones, UTC and local differ by at least 1 hour
        # This test might not be perfect for UTC timezone, but validates the intent
        # We can't assert they're different because the test might run in UTC timezone

    @patch("requests.post")
    def test_post_with_retry_success_first_attempt(self, mock_post):
        """Test successful request on first attempt."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = usage.post_with_retry("http://test.com", {"data": "test"})
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(mock_post.call_count, 1)

    @patch("time.sleep")
    @patch("requests.post")
    def test_post_with_retry_success_after_retries(self, mock_post, mock_sleep):
        """Test successful request after transient failures."""
        # First two attempts fail with 503, third succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.ok = False
        mock_response_fail.status_code = 503

        mock_response_success = MagicMock()
        mock_response_success.ok = True
        mock_response_success.status_code = 200

        mock_post.side_effect = [mock_response_fail, mock_response_fail, mock_response_success]

        result = usage.post_with_retry("http://test.com", {"data": "test"}, max_retries=3)
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)  # Sleep before retry 2 and 3

    @patch("time.sleep")
    @patch("requests.post")
    def test_post_with_retry_exponential_backoff(self, mock_post, mock_sleep):
        """Test exponential backoff timing."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 503
        mock_post.return_value = mock_response

        usage.post_with_retry("http://test.com", {"data": "test"}, max_retries=3, backoff_factor=2.0)

        # Verify exponential backoff: 2^0=1, 2^1=2 seconds
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_any_call(1.0)  # 2^0
        mock_sleep.assert_any_call(2.0)  # 2^1

    @patch("requests.post")
    def test_post_with_retry_non_retriable_4xx(self, mock_post):
        """Test non-retriable 4xx errors (except 429) don't retry."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 400
        mock_post.return_value = mock_response

        result = usage.post_with_retry("http://test.com", {"data": "test"})
        self.assertIsNotNone(result)
        self.assertFalse(result.ok)
        self.assertEqual(result.status_code, 400)
        # Should not retry for 400 error
        self.assertEqual(mock_post.call_count, 1)

    @patch("time.sleep")
    @patch("requests.post")
    def test_post_with_retry_rate_limit_429(self, mock_post, mock_sleep):
        """Test rate limit 429 errors are retried."""
        mock_response_429 = MagicMock()
        mock_response_429.ok = False
        mock_response_429.status_code = 429

        mock_response_success = MagicMock()
        mock_response_success.ok = True
        mock_response_success.status_code = 200

        mock_post.side_effect = [mock_response_429, mock_response_success]

        result = usage.post_with_retry("http://test.com", {"data": "test"})
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch("time.sleep")
    @patch("requests.post")
    def test_post_with_retry_connection_error(self, mock_post, mock_sleep):
        """Test connection errors are retried."""
        mock_post.side_effect = [
            requests.ConnectionError("Network error"),
            requests.ConnectionError("Network error"),
            MagicMock(ok=True, status_code=200),
        ]

        result = usage.post_with_retry("http://test.com", {"data": "test"}, max_retries=3)
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(mock_post.call_count, 3)

    @patch("time.sleep")
    @patch("requests.post")
    def test_post_with_retry_timeout_error(self, mock_post, mock_sleep):
        """Test timeout errors are retried."""
        mock_post.side_effect = [
            requests.Timeout("Request timeout"),
            MagicMock(ok=True, status_code=200),
        ]

        result = usage.post_with_retry("http://test.com", {"data": "test"})
        self.assertIsNotNone(result)
        self.assertTrue(result.ok)
        self.assertEqual(mock_post.call_count, 2)

    @patch("time.sleep")
    @patch("requests.post")
    def test_post_with_retry_exhausted_retries(self, mock_post, mock_sleep):
        """Test all retries exhausted returns None."""
        mock_post.side_effect = requests.ConnectionError("Network error")

        result = usage.post_with_retry("http://test.com", {"data": "test"}, max_retries=3)
        self.assertIsNone(result)
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("requests.post")
    def test_post_with_retry_unexpected_exception(self, mock_post):
        """Test unexpected exceptions don't retry."""
        mock_post.side_effect = ValueError("Unexpected error")

        result = usage.post_with_retry("http://test.com", {"data": "test"})
        self.assertIsNone(result)
        # Should not retry on unexpected exceptions
        self.assertEqual(mock_post.call_count, 1)

    @patch("time.sleep")
    @patch("requests.post")
    def test_post_with_retry_server_errors_5xx(self, mock_post, mock_sleep):
        """Test server errors (5xx) are retried."""
        for status_code in [500, 502, 503, 504]:
            mock_post.reset_mock()
            mock_sleep.reset_mock()

            mock_response = MagicMock()
            mock_response.ok = False
            mock_response.status_code = status_code
            mock_post.return_value = mock_response

            result = usage.post_with_retry("http://test.com", {"data": "test"}, max_retries=2)
            self.assertIsNone(result)
            self.assertEqual(mock_post.call_count, 2)
            self.assertEqual(mock_sleep.call_count, 1)

    @patch("time.sleep")
    @patch("src.usage.post_with_retry")
    def test_post_new_installation_with_retry(self, mock_retry, mock_sleep):
        """Test post_new_installation uses retry logic."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": str(uuid.uuid4())}
        mock_retry.return_value = mock_response

        result = usage.post_new_installation({"test": "data"}, "http://test.com")
        self.assertIsNotNone(result)
        mock_retry.assert_called_once_with("http://test.com", {"test": "data"}, timeout=10)

    @patch("time.sleep")
    @patch("src.usage.post_with_retry")
    def test_post_new_heartbeat_with_retry(self, mock_retry, mock_sleep):
        """Test post_new_heartbeat uses retry logic."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 201
        mock_retry.return_value = mock_response

        result = usage.post_new_heartbeat({"test": "data"}, "http://test.com")
        self.assertTrue(result)
        mock_retry.assert_called_once_with("http://test.com", {"test": "data"}, timeout=20)

    @patch("time.sleep")
    @patch("src.usage.post_with_retry")
    def test_post_new_installation_retry_failure(self, mock_retry, mock_sleep):
        """Test post_new_installation handles retry failure."""
        mock_retry.return_value = None  # All retries failed

        result = usage.post_new_installation({"test": "data"}, "http://test.com")
        self.assertIsNone(result)

    @patch("time.sleep")
    @patch("src.usage.post_with_retry")
    def test_post_new_heartbeat_retry_failure(self, mock_retry, mock_sleep):
        """Test post_new_heartbeat handles retry failure."""
        mock_retry.return_value = None  # All retries failed

        result = usage.post_new_heartbeat({"test": "data"}, "http://test.com")
        self.assertFalse(result)

    def test_retry_env_variables(self):
        """Test retry configuration from environment variables."""
        # Test default values
        self.assertEqual(usage.MAX_RETRIES, 3)
        self.assertEqual(usage.RETRY_BACKOFF_FACTOR, 2.0)

    @patch("src.usage.post_with_retry")
    def test_post_new_installation_exception_handling(self, mock_retry):
        """Test post_new_installation handles exceptions in response processing."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.side_effect = ValueError("JSON decode error")
        mock_retry.return_value = mock_response

        result = usage.post_new_installation({"test": "data"}, "http://test.com")
        self.assertIsNone(result)

    @patch("src.usage.post_with_retry")
    def test_post_new_heartbeat_exception_handling(self, mock_retry):
        """Test post_new_heartbeat handles exceptions in response processing."""
        mock_response = MagicMock()
        mock_response.ok = True
        # Simulate exception during response processing
        type(mock_response).ok = property(lambda self: (_ for _ in ()).throw(ValueError("Error")))
        mock_retry.return_value = mock_response

        result = usage.post_new_heartbeat({"test": "data"}, "http://test.com")
        self.assertFalse(result)
