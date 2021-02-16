__author__ = 'Mandar Patil (mandarons@pm.me)'

import os

DEFAULT_DRIVE_DESTINATION = './drive'
DEFAULT_CONFIG_FILE_NAME = 'config.yaml'
DEFAULT_CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), DEFAULT_CONFIG_FILE_NAME)
DEFAULT_SYNC_INTERVAL_SEC = 1800  # 30 minutes
