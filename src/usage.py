"""To record usage of the app."""

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any

import requests

from src import get_logger
from src.config_parser import get_usage_tracking_enabled, prepare_root_destination

LOGGER = get_logger()

# Filename for the usage cache.  Stored under the root destination
# directory (``app.root``) via ``init_cache()``.  Kept as a bare
# filename so that ``init_cache`` controls where the cache lives.
CACHE_FILE_NAME = ".data"
NEW_INSTALLATION_ENDPOINT = os.environ.get("NEW_INSTALLATION_ENDPOINT", None)
NEW_HEARTBEAT_ENDPOINT = os.environ.get("NEW_HEARTBEAT_ENDPOINT", None)
APP_NAME = "icloud-docker"
APP_VERSION = os.environ.get("APP_VERSION", "dev")
NEW_INSTALLATION_DATA = {"appName": APP_NAME, "appVersion": APP_VERSION}

# Retry configuration
MAX_RETRIES = int(os.environ.get("USAGE_TRACKING_MAX_RETRIES", "3"))
RETRY_BACKOFF_FACTOR = float(os.environ.get("USAGE_TRACKING_RETRY_BACKOFF", "2.0"))


def init_cache(config: dict) -> str:
    """Initialize the cache file.

    Args:
        config: Configuration dictionary containing root destination path

    Returns:
        Absolute path to the cache file
    """
    root_destination_path = prepare_root_destination(config=config)
    cache_file_path = os.path.join(root_destination_path, CACHE_FILE_NAME)
    LOGGER.debug(f"Initialized usage cache at: {cache_file_path}")
    return cache_file_path


def validate_cache_data(data: dict) -> bool:
    """Validate cache data structure.

    Args:
        data: Dictionary to validate

    Returns:
        True if data is valid, False otherwise
    """
    # Basic structure validation
    if not isinstance(data, dict):
        return False

    # If we have an ID, validate it's a string
    if "id" in data and not isinstance(data["id"], str):
        return False

    # If we have app_version, validate it's a string
    if "app_version" in data and not isinstance(data["app_version"], str):
        return False

    # If we have heartbeat timestamp, validate format.
    # Accept both ``%Y-%m-%d %H:%M:%S.%f`` (current) and
    # ``%Y-%m-%d %H:%M:%S`` (legacy, microsecond zero) to avoid
    # wiping old caches that were written by the str() method.
    if "heartbeat_timestamp" in data:
        ts = data["heartbeat_timestamp"]
        if not isinstance(ts, str):
            return False
        try:
            datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f")
        except (ValueError, TypeError):
            try:
                datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                return False

    return True


def load_cache(file_path: str) -> dict:
    """Load the cache file with validation and corruption recovery.

    Args:
        file_path: Absolute path to the cache file

    Returns:
        Dictionary containing cached usage data
    """
    data = {}
    if os.path.isfile(file_path):
        try:
            with open(file_path, encoding="utf-8") as f:
                loaded_data = json.load(f)

            # Validate the loaded data
            if validate_cache_data(loaded_data):
                data = loaded_data
                LOGGER.debug(f"Loaded and validated usage cache from: {file_path}")
            else:
                LOGGER.debug(f"Cache data validation failed for {file_path}, starting fresh")
                save_cache(file_path=file_path, data={})
        except (json.JSONDecodeError, OSError) as e:
            LOGGER.debug(f"Failed to load usage cache from {file_path}: {e}")
            LOGGER.debug("Creating new empty cache file due to corruption")
            save_cache(file_path=file_path, data={})
    else:
        LOGGER.debug(f"Usage cache file not found, creating: {file_path}")
        save_cache(file_path=file_path, data={})
    return data


def save_cache(file_path: str, data: dict) -> bool:
    """Save data to the cache file using atomic operations.

    Args:
        file_path: Absolute path to the cache file
        data: Dictionary containing usage data to save

    Returns:
        True if save was successful, False otherwise
    """
    try:
        # Write to temporary file first for atomic operation
        dir_name = os.path.dirname(file_path)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=dir_name,
            delete=False,
            suffix=".tmp",
        ) as temp_file:
            json.dump(data, temp_file, indent=2)
            temp_path = temp_file.name

        # Atomically move temp file to final location
        os.rename(temp_path, file_path)
        LOGGER.debug(f"Atomically saved usage cache to: {file_path}")
        return True
    except OSError as e:
        LOGGER.debug(f"Failed to save usage cache to {file_path}: {e}")
        # Clean up temp file if it exists
        try:
            if "temp_path" in locals():
                os.unlink(temp_path)
        except OSError:
            pass
        return False


def post_with_retry(
    url: str,
    json_data: dict,
    timeout: int = 10,
    max_retries: int = MAX_RETRIES,
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
) -> requests.Response | None:
    """Post request with exponential backoff retry.

    Args:
        url: Endpoint URL
        json_data: JSON payload
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for exponential backoff

    Returns:
        Response object if successful, None otherwise
    """
    last_exception = None
    last_response = None

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=json_data, timeout=timeout)  # type: ignore[arg-type]

            # Don't retry on validation errors (4xx except rate limit)
            if 400 <= response.status_code < 500 and response.status_code != 429:
                LOGGER.debug(f"Non-retriable error (status {response.status_code})")
                return response

            # Success or retriable error
            if response.ok:
                return response

            # Rate limit (429) or server error (5xx) - retry
            last_response = response
            LOGGER.debug(
                f"Request failed with status {response.status_code}, attempt {attempt + 1}/{max_retries}",
            )

        except (requests.ConnectionError, requests.Timeout) as e:
            last_exception = e
            LOGGER.debug(f"Network error: {e}, attempt {attempt + 1}/{max_retries}")
        except Exception as e:
            # Catch other exceptions but don't retry
            LOGGER.debug(f"Unexpected error during request: {e}")
            return None

        # Exponential backoff before next retry
        if attempt < max_retries - 1:
            wait_time = backoff_factor**attempt
            LOGGER.debug(f"Waiting {wait_time}s before retry...")
            time.sleep(wait_time)

    # All retries exhausted — return the last response (if any) so callers
    # can distinguish server errors from network failures.
    if last_response is not None:
        LOGGER.debug(f"All retry attempts failed: HTTP {last_response.status_code}")
        return last_response
    if last_exception:
        LOGGER.debug(f"All retry attempts failed: {last_exception}")
    return None


def post_new_installation(data: dict, endpoint=NEW_INSTALLATION_ENDPOINT) -> str | None:
    """Post new installation to server with retry logic.

    Args:
        data: Dictionary containing installation data
        endpoint: API endpoint URL, defaults to NEW_INSTALLATION_ENDPOINT

    Returns:
        Installation ID if successful, None otherwise
    """
    try:
        LOGGER.debug(f"Posting new installation to: {endpoint}")
        response = post_with_retry(endpoint, data, timeout=10)

        if response and response.ok:
            response_data = response.json()
            installation_id = response_data["id"]
            LOGGER.debug(f"Successfully registered new installation: {installation_id}")
            return installation_id
        else:
            status = response.status_code if response else "no response"
            LOGGER.debug(f"Installation registration failed: {status}")
    except Exception as e:
        LOGGER.debug(f"Failed to post new installation: {e}")
    return None


def record_new_installation(previous_id: str | None = None) -> str | None:
    """Record new or upgrade existing installation.

    Args:
        previous_id: Previous installation ID for upgrades, None for new installations

    Returns:
        New installation ID if successful, None otherwise
    """
    data = dict(NEW_INSTALLATION_DATA)
    if previous_id:
        data["previousId"] = previous_id
    return post_new_installation(data)


def already_installed(cached_data: dict) -> bool:
    """Check if already installed.

    Args:
        cached_data: Dictionary containing cached usage data

    Returns:
        True if installation is up-to-date, False otherwise
    """
    return "id" in cached_data and "app_version" in cached_data and cached_data["app_version"] == APP_VERSION


def install(cached_data: dict) -> dict | None:
    """Install the app.

    Args:
        cached_data: Dictionary containing cached usage data

    Returns:
        Updated cached data dictionary if successful, None otherwise
    """
    previous_id = cached_data.get("id", None)
    if previous_id:
        LOGGER.debug(f"Upgrading existing installation: {previous_id}")
    else:
        LOGGER.debug("Installing new instance")

    new_id = record_new_installation(previous_id)
    if new_id:
        cached_data["id"] = new_id
        cached_data["app_version"] = APP_VERSION
        LOGGER.debug(f"Installation completed with ID: {new_id}")
        return cached_data

    LOGGER.debug("Installation failed")
    return None


def post_new_heartbeat(data: dict, endpoint=NEW_HEARTBEAT_ENDPOINT) -> bool:
    """Post the heartbeat to server with retry logic.

    Args:
        data: Dictionary containing heartbeat data
        endpoint: API endpoint URL, defaults to NEW_HEARTBEAT_ENDPOINT

    Returns:
        True if heartbeat was sent successfully, False otherwise
    """
    try:
        LOGGER.debug(f"Posting heartbeat to: {endpoint}")
        response = post_with_retry(endpoint, data, timeout=20)

        if response and response.ok:
            LOGGER.debug("Heartbeat sent successfully")
            return True
        else:
            status = response.status_code if response else "no response"
            LOGGER.debug(f"Heartbeat failed: {status}")
    except Exception as e:
        LOGGER.debug(f"Failed to post heartbeat: {e}")
    return False


def send_heartbeat(app_id: str | None, data: Any = None) -> bool:
    """Prepare and send heartbeat to server.

    Args:
        app_id: Installation ID for heartbeat identification
        data: Additional data to send with heartbeat

    Returns:
        True if heartbeat was sent successfully, False otherwise
    """
    data = {"installationId": app_id, "data": data}
    return post_new_heartbeat(data)


def _format_timestamp(dt: datetime) -> str:
    """Format a datetime as a cache-friendly string.

    Uses explicit ``strftime`` so that the microsecond field is always
    present (``str(datetime)`` omits it when microseconds are zero,
    which would crash ``strptime`` with ``%f`` on load).
    """
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")


def _parse_timestamp(ts: str) -> datetime:
    """Parse a timestamp string produced by ``_format_timestamp``.

    Accepts the ``%f``-fractional format.  Returns a timezone-aware UTC
    datetime (``tzinfo=timezone.utc``) so it can be compared against
    ``current_time()``'s output without naive/aware mismatches.
    """
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)


def current_time() -> datetime:
    """Get current UTC time.

    Returns:
        Current UTC datetime object (timezone-aware)
    """
    return datetime.now(timezone.utc)


def heartbeat(cached_data: dict, data: Any) -> dict | None:
    """Send heartbeat.

    Args:
        cached_data: Dictionary containing cached usage data
        data: Additional data to send with heartbeat

    Returns:
        Updated cached data dictionary if heartbeat was sent,
        None if heartbeat was throttled or failed
    """
    previous_heartbeat = cached_data.get("heartbeat_timestamp", None)
    current = current_time()

    if previous_heartbeat:
        try:
            previous = _parse_timestamp(previous_heartbeat)
            time_since_last = current - previous
            LOGGER.debug(f"Time since last heartbeat: {time_since_last}")

            # Check if different UTC day, not just 24 hours
            if previous.date() < current.date():
                LOGGER.debug("Sending heartbeat (different UTC day)")
                if send_heartbeat(cached_data.get("id"), data=data):
                    cached_data["heartbeat_timestamp"] = _format_timestamp(current)
                    return cached_data
                else:
                    LOGGER.debug("Heartbeat send failed")
                    return None
            else:
                LOGGER.debug("Heartbeat throttled (same UTC day)")
                return None
        except ValueError as e:
            LOGGER.debug(f"Invalid heartbeat timestamp format: {e}")
            # Treat as first heartbeat if timestamp is invalid

    # First heartbeat or invalid timestamp
    LOGGER.debug("Sending first heartbeat")
    if send_heartbeat(cached_data.get("id"), data=data):
        cached_data["heartbeat_timestamp"] = _format_timestamp(current)
        LOGGER.debug("First heartbeat sent successfully")
        return cached_data
    else:
        LOGGER.debug("First heartbeat send failed")
        return None


def alive(config: dict | None, data: Any = None) -> bool:
    """Record liveliness.

    Args:
        config: Configuration dictionary (or None to skip tracking)
        data: Additional usage data to send with heartbeat

    Returns:
        True if usage tracking was successful (or skipped), False on failure
    """
    # Guard: missing config — skip silently
    if config is None:
        return True

    # Check if usage tracking is disabled
    if not get_usage_tracking_enabled(config):
        LOGGER.debug("Usage tracking is disabled, skipping")
        return True  # Return True to not affect main sync loop

    LOGGER.debug("Usage tracking alive check started")

    cache_file_path = init_cache(config=config)
    cached_data = load_cache(cache_file_path)

    if not already_installed(cached_data=cached_data):
        LOGGER.debug("New installation detected, registering...")
        installed_data = install(cached_data=cached_data)
        if installed_data is not None:
            result = save_cache(file_path=cache_file_path, data=installed_data)
            LOGGER.debug("Installation registration completed")
            return result
        else:
            LOGGER.debug("Installation registration failed")
            return False

    LOGGER.debug("Installation already registered, checking heartbeat")
    heartbeat_data = heartbeat(cached_data=cached_data, data=data)
    if heartbeat_data is not None:
        result = save_cache(file_path=cache_file_path, data=heartbeat_data)
        LOGGER.debug("Heartbeat completed successfully")
        return result

    LOGGER.debug("No heartbeat required or heartbeat failed")
    return True
