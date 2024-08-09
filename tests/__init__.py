"""Tests module."""

__author__ = "Mandar Patil (mandarons@pm.me)"

import os
import uuid

from ruamel.yaml import YAML

from src import usage

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CONFIG_PATH = os.path.join(DATA_DIR, "test_config.yaml")
ENV_CONFIG_PATH = os.path.join(DATA_DIR, "test_config_env.yaml")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
DRIVE_DIR = os.path.join(TEMP_DIR, "icloud", "drive")
PHOTOS_DIR = os.path.join(TEMP_DIR, "icloud", "photos")


def update_config(data):
    """Update config test config path."""
    return YAML().dump(data=data, stream=open(file=CONFIG_PATH, mode="w", encoding="utf-8"))


def mocked_usage_post(*args, **kwargs):
    """Mock the post method."""

    class MockResponse:
        def __init__(self, json_data, status_code) -> None:
            self.json_data = json_data
            self.status_code = status_code
            self.ok = status_code == 201

        def json(self):
            return self.json_data

    if args[0] is usage.NEW_INSTALLATION_ENDPOINT:
        return MockResponse({"id": str(uuid.uuid4())}, 201)
    elif args[0] is usage.NEW_HEARTBEAT_ENDPOINT:
        return MockResponse({"message": "All good."}, 201)
    return MockResponse(None, 404)
