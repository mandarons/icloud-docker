"""To record usage of the app."""

import json
import os
from datetime import datetime, timedelta

import requests

from src.config_parser import prepare_root_destination

CACHE_FILE_NAME = "/config/.data"
NEW_INSTALLATION_ENDPOINT = os.environ.get("NEW_INSTALLATION_ENDPOINT", None)
NEW_HEARTBEAT_ENDPOINT = os.environ.get("NEW_HEARTBEAT_ENDPOINT", None)
APP_NAME = "icloud-drive-docker"
APP_VERSION = os.environ.get("APP_VERSION", "dev")
NEW_INSTALLATION_DATA = {"appName": APP_NAME, "appVersion": APP_VERSION}


def init_cache(config):
    """Initialize the cache file."""
    root_destination_path = prepare_root_destination(config=config)
    cache_file_path = os.path.join(root_destination_path, CACHE_FILE_NAME)
    return cache_file_path


def load_cache(file_path: str):
    """Load the cache file."""
    data = {}
    if os.path.isfile(file_path):
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    else:
        save_cache(file_path=file_path, data={})
    return data


def save_cache(file_path: str, data: object):
    """Save data to the cache file."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return True


def post_new_installation(data, endpoint=NEW_INSTALLATION_ENDPOINT):
    """Post new installation to server."""
    try:
        response = requests.post(endpoint, data, timeout=10000)
        if response.ok:
            data = response.json()
            return data["id"]
    except Exception:
        pass
    return None


def record_new_installation(previous_id=None):
    """Record new or upgrade existing installation."""
    data = dict(NEW_INSTALLATION_DATA)
    if previous_id:
        data["previousId"] = previous_id
    return post_new_installation(data)


def already_installed(cached_data):
    """Check if already installed."""
    return "id" in cached_data and "app_version" in cached_data and cached_data["app_version"] == APP_VERSION


def install(cached_data):
    """Install the app."""
    new_id = record_new_installation(cached_data.get("id", None))
    if new_id:
        cached_data["id"] = new_id
        cached_data["app_version"] = APP_VERSION
        return cached_data
    return False


def post_new_heartbeat(data, endpoint=NEW_HEARTBEAT_ENDPOINT):
    """Post the heartbeat to server."""
    try:
        response = requests.post(endpoint, data, timeout=10000)
        if response.ok:
            return True
    except Exception:
        pass
    return False


def send_heartbeat(app_id, data=None):
    """Prepare and send heartbeat to server."""
    data = {"installationId": app_id, "data": data}
    return post_new_heartbeat(data)


def current_time():
    """Get current time."""
    return datetime.now()


def heartbeat(cached_data, data):
    """Send heartbeat."""
    previous_heartbeat = cached_data.get("heartbeat_timestamp", None)
    current = current_time()
    if previous_heartbeat:
        previous = datetime.strptime(previous_heartbeat, "%Y-%m-%d %H:%M:%S.%f")
        if previous < (current - timedelta(hours=24)):
            if send_heartbeat(cached_data.get("id"), data=data):
                cached_data["heartbeat_timestamp"] = str(current)
                return cached_data
        else:
            return False
    elif send_heartbeat(cached_data.get("id"), data=data):
        cached_data["heartbeat_timestamp"] = str(current)
        return cached_data


def alive(config, data=None):
    """Record liveliness."""
    cache_file_path = init_cache(config=config)
    cached_data = load_cache(cache_file_path)
    if not already_installed(cached_data=cached_data):
        installed_data = install(cached_data=cached_data)
        if installed_data:
            return save_cache(file_path=cache_file_path, data=installed_data)
    heartbeat_data = heartbeat(cached_data=cached_data, data=data)
    if heartbeat_data:
        return save_cache(file_path=cache_file_path, data=heartbeat_data)
    return False
