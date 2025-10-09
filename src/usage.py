"""To record usage of the app."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Any

import requests

from src import get_logger
from src.config_parser import get_usage_tracking_enabled, prepare_root_destination

LOGGER = get_logger()

CACHE_FILE_NAME = "/config/.data"
NEW_INSTALLATION_ENDPOINT = os.environ.get("NEW_INSTALLATION_ENDPOINT", None)
NEW_HEARTBEAT_ENDPOINT = os.environ.get("NEW_HEARTBEAT_ENDPOINT", None)
APP_NAME = "icloud-drive-docker"
APP_VERSION = os.environ.get("APP_VERSION", "dev")
NEW_INSTALLATION_DATA = {"appName": APP_NAME, "appVersion": APP_VERSION}


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

    # If we have heartbeat timestamp, validate format
    if "heartbeat_timestamp" in data:
        try:
            datetime.strptime(data["heartbeat_timestamp"], "%Y-%m-%d %H:%M:%S.%f")
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
                LOGGER.warning(f"Cache data validation failed for {file_path}, starting fresh")
                save_cache(file_path=file_path, data={})
        except (json.JSONDecodeError, OSError) as e:
            LOGGER.error(f"Failed to load usage cache from {file_path}: {e}")
            LOGGER.info("Creating new empty cache file due to corruption")
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
        LOGGER.error(f"Failed to save usage cache to {file_path}: {e}")
        # Clean up temp file if it exists
        try:
            if "temp_path" in locals():
                os.unlink(temp_path)
        except OSError:
            pass
        return False


def post_new_installation(data: dict, endpoint=NEW_INSTALLATION_ENDPOINT) -> str | None:
    """Post new installation to server.

    Args:
        data: Dictionary containing installation data
        endpoint: API endpoint URL, defaults to NEW_INSTALLATION_ENDPOINT

    Returns:
        Installation ID if successful, None otherwise
    """
    try:
        LOGGER.debug(f"Posting new installation to: {endpoint}")
        response = requests.post(endpoint, json=data, timeout=5000)  # type: ignore[arg-type]
        if response.ok:
            response_data = response.json()
            installation_id = response_data["id"]
            LOGGER.info(f"Successfully registered new installation: {installation_id}")
            return installation_id
        else:
            LOGGER.warning(f"Installation registration failed with status {response.status_code}")
    except Exception as e:
        LOGGER.error(f"Failed to post new installation: {e}")
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
        LOGGER.info(f"Upgrading existing installation: {previous_id}")
    else:
        LOGGER.info("Installing new instance")

    new_id = record_new_installation(previous_id)
    if new_id:
        cached_data["id"] = new_id
        cached_data["app_version"] = APP_VERSION
        LOGGER.info(f"Installation completed with ID: {new_id}")
        return cached_data

    LOGGER.error("Installation failed")
    return None


def post_new_heartbeat(data: dict, endpoint=NEW_HEARTBEAT_ENDPOINT) -> bool:
    """Post the heartbeat to server.

    Args:
        data: Dictionary containing heartbeat data
        endpoint: API endpoint URL, defaults to NEW_HEARTBEAT_ENDPOINT

    Returns:
        True if heartbeat was sent successfully, False otherwise
    """
    try:
        LOGGER.debug(f"Posting heartbeat to: {endpoint}")
        response = requests.post(endpoint, json=data, timeout=5000)  # type: ignore[arg-type]
        if response.ok:
            LOGGER.debug("Heartbeat sent successfully")
            return True
        else:
            LOGGER.warning(f"Heartbeat failed with status {response.status_code}")
    except Exception as e:
        LOGGER.error(f"Failed to post heartbeat: {e}")
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


def current_time() -> datetime:
    """Get current time.

    Returns:
        Current datetime object
    """
    return datetime.now()


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
            previous = datetime.strptime(previous_heartbeat, "%Y-%m-%d %H:%M:%S.%f")
            time_since_last = current - previous
            LOGGER.debug(f"Time since last heartbeat: {time_since_last}")

            if previous < (current - timedelta(hours=24)):
                LOGGER.debug("Sending heartbeat (24+ hours since last)")
                if send_heartbeat(cached_data.get("id"), data=data):
                    cached_data["heartbeat_timestamp"] = str(current)
                    return cached_data
                else:
                    LOGGER.warning("Heartbeat send failed")
                    return None
            else:
                LOGGER.debug("Heartbeat throttled (less than 24 hours)")
                return None
        except ValueError as e:
            LOGGER.error(f"Invalid heartbeat timestamp format: {e}")
            # Treat as first heartbeat if timestamp is invalid

    # First heartbeat or invalid timestamp
    LOGGER.debug("Sending first heartbeat")
    if send_heartbeat(cached_data.get("id"), data=data):
        cached_data["heartbeat_timestamp"] = str(current)
        LOGGER.debug("First heartbeat sent successfully")
        return cached_data
    else:
        LOGGER.warning("First heartbeat send failed")
        return None


def alive(config: dict, data: Any = None) -> bool:
    """Record liveliness.

    Args:
        config: Configuration dictionary
        data: Additional usage data to send with heartbeat

    Returns:
        True if usage tracking was successful, False otherwise
    """
    # Check if usage tracking is disabled
    if not get_usage_tracking_enabled(config):
        LOGGER.debug("Usage tracking is disabled, skipping")
        return True  # Return True to not affect main sync loop

    LOGGER.debug("Usage tracking alive check started")

    cache_file_path = init_cache(config=config)
    cached_data = load_cache(cache_file_path)

    if not already_installed(cached_data=cached_data):
        LOGGER.info("New installation detected, registering...")
        installed_data = install(cached_data=cached_data)
        if installed_data is not None:
            result = save_cache(file_path=cache_file_path, data=installed_data)
            LOGGER.info("Installation registration completed")
            return result
        else:
            LOGGER.error("Installation registration failed")
            return False

    LOGGER.debug("Installation already registered, checking heartbeat")
    heartbeat_data = heartbeat(cached_data=cached_data, data=data)
    if heartbeat_data is not None:
        result = save_cache(file_path=cache_file_path, data=heartbeat_data)
        LOGGER.debug("Heartbeat completed successfully")
        return result

    LOGGER.debug("No heartbeat required or heartbeat failed")
    return False
