__author__ = 'Mandar Patil (mandarons@pm.me)'

import os
from ruamel.yaml import YAML

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
CONFIG_PATH = os.path.join(DATA_DIR, 'test_config.yaml')
TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp')
DRIVE_DIR = os.path.join(TEMP_DIR, 'icloud', 'drive')


def update_config(data):
    return YAML().dump(data=data, stream=open(file=CONFIG_PATH, mode='w'))
