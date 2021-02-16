__author__ = 'Mandar Patil (mandarons@pm.me)'

import os
from ruamel.yaml import YAML
from src import constants


def read_config(config_path=constants.DEFAULT_CONFIG_FILE_PATH):
    if not (config_path and os.path.exists(config_path)):
        print(f'Error: Config file not found at {config_path}.')
        return None
    with open(file=config_path, mode='r') as config_file:
        config = YAML().load(config_file)
    config['credentials']['username'] = config['credentials']['username'].strip() \
        if config['credentials']['username'] is not None else ''
    return config


def get_sync_interval(config):
    sync_interval = constants.DEFAULT_SYNC_INTERVAL_SEC
    if not (config and 'settings' in config and 'sync_interval' in config['settings']):
        print(f'Warning: sync_interval is not found in config > settings. Using default sync_interval: '
              f'{sync_interval} seconds ...')
    else:
        sync_interval = config['settings']['sync_interval']
        print(f'Syncing every {sync_interval} seconds.')
    return sync_interval


def prepare_destination(config):
    print('Checking drive location ...')
    destination = constants.DEFAULT_DRIVE_DESTINATION
    if not (config and 'settings' in config and 'destination' in config['settings']):
        print(f'Warning: destination is missing in config > settings. Using default destination: {destination}.')
    else:
        destination = config['settings']['destination']
    destination_path = os.path.abspath(destination)
    os.makedirs(destination_path, exist_ok=True)
    return destination_path


def get_username(config):
    username = None
    if not (config and 'credentials' in config and 'username' in config['credentials']):
        print('Error: username is missing in config > credentials. Please set the username.')
    else:
        username = config['credentials']['username']
        username = username.strip()
        if len(username) == 0:
            username = None
            print('Error: username is empty in config > credentials.')
    return username


def get_remove_obsolete(config):
    remove_obsolete = False
    if not (config and 'settings' in config and 'remove_obsolete' in config['settings']):
        print(
            'Warning: remove_obsolete is not found in config > settings. Not removing the obsolete files and folders.')
    else:
        remove_obsolete = config['settings']['remove_obsolete']
        print('Removing obsolete files and folders ...')
    return remove_obsolete


def get_verbose(config):
    verbose = False
    if not (config and 'settings' in config and 'verbose' in config['settings']):
        print('Warning: verbose is not found in config > settings. Disabling verbose mode.')
    else:
        verbose = config['settings']['verbose']
        print('Enabled verbose ...')
    return verbose
