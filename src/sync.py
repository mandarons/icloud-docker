"""Sync module."""

__author__ = "Mandar Patil <mandarons@pm.me>"
import datetime
import os
from time import sleep

from icloudpy import ICloudPyService, exceptions, utils

from src import (
    DEFAULT_CONFIG_FILE_PATH,
    DEFAULT_COOKIE_DIRECTORY,
    ENV_CONFIG_FILE_PATH_KEY,
    ENV_ICLOUD_PASSWORD_KEY,
    config_parser,
    get_logger,
    notify,
    read_config,
    sync_drive,
    sync_photos,
)
from src.usage import alive

LOGGER = get_logger()


def get_api_instance(
    username,
    password,
    cookie_directory=DEFAULT_COOKIE_DIRECTORY,
    server_region="global",
):
    """Get API client instance."""
    return (
        ICloudPyService(
            apple_id=username,
            password=password,
            cookie_directory=cookie_directory,
            home_endpoint="https://www.icloud.com.cn",
            setup_endpoint="https://setup.icloud.com.cn/setup/ws/1",
        )
        if server_region == "china"
        else ICloudPyService(
            apple_id=username,
            password=password,
            cookie_directory=cookie_directory,
        )
    )


def sync():
    """Sync data from server."""
    last_send = None
    enable_sync_drive = True
    enable_sync_photos = True
    drive_sync_interval = 0
    photos_sync_interval = 0
    sleep_for = 10

    while True:
        config = read_config(config_path=os.environ.get(ENV_CONFIG_FILE_PATH_KEY, DEFAULT_CONFIG_FILE_PATH))
        alive(config=config)
        username = config_parser.get_username(config=config)
        if username:
            try:
                server_region = config_parser.get_region(config=config)
                if ENV_ICLOUD_PASSWORD_KEY in os.environ:
                    password = os.environ.get(ENV_ICLOUD_PASSWORD_KEY)
                    utils.store_password_in_keyring(username=username, password=password)
                else:
                    password = utils.get_password_from_keyring(username=username)
                api = get_api_instance(username=username, password=password, server_region=server_region)
                if not api.requires_2sa:
                    if "drive" in config and enable_sync_drive:
                        LOGGER.info("Syncing drive...")
                        sync_drive.sync_drive(config=config, drive=api.drive)
                        LOGGER.info("Drive synced")
                        drive_sync_interval = config_parser.get_drive_sync_interval(config=config)
                    if "photos" in config and enable_sync_photos:
                        LOGGER.info("Syncing photos...")
                        sync_photos.sync_photos(config=config, photos=api.photos)
                        LOGGER.info("Photos synced")
                        photos_sync_interval = config_parser.get_photos_sync_interval(config=config)
                    if "drive" not in config and "photos" not in config:
                        LOGGER.warning("Nothing to sync. Please add drive: and/or photos: section in config.yaml file.")
                else:
                    LOGGER.error("Error: 2FA is required. Please log in.")
                    # Retry again
                    sleep_for = config_parser.get_retry_login_interval(config=config)
                    if sleep_for < 0:
                        LOGGER.info("retry_login_interval is < 0, exiting ...")
                        break
                    next_sync = (datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)).strftime("%c")
                    LOGGER.info(f"Retrying login at {next_sync} ...")
                    last_send = notify.send(config=config, username=username, last_send=last_send, region=server_region)
                    sleep(sleep_for)
                    continue
            except exceptions.ICloudPyNoStoredPasswordAvailableException:
                LOGGER.error("Password is not stored in keyring. Please save the password in keyring.")
                sleep_for = config_parser.get_retry_login_interval(config=config)
                if sleep_for < 0:
                    LOGGER.info("retry_login_interval is < 0, exiting ...")
                    break
                next_sync = (datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)).strftime("%c")
                LOGGER.info(f"Retrying login at {next_sync} ...")
                last_send = notify.send(config=config, username=username, last_send=last_send, region=server_region)
                sleep(sleep_for)
                continue

        if "drive" not in config and "photos" in config:
            sleep_for = photos_sync_interval
            enable_sync_drive = False
            enable_sync_photos = True
        elif "drive" in config and "photos" not in config:
            sleep_for = drive_sync_interval
            enable_sync_drive = True
            enable_sync_photos = False
        elif "drive" in config and "photos" in config and drive_sync_interval <= photos_sync_interval:
            sleep_for = photos_sync_interval - drive_sync_interval
            photos_sync_interval -= drive_sync_interval
            enable_sync_drive = True
            enable_sync_photos = False
        else:
            sleep_for = drive_sync_interval - photos_sync_interval
            drive_sync_interval -= photos_sync_interval
            enable_sync_drive = False
            enable_sync_photos = True
        next_sync = (datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)).strftime("%c")
        LOGGER.info(f"Resyncing at {next_sync} ...")
        if (
            config_parser.get_drive_sync_interval(config=config) < 0
            if "drive" in config
            else True and config_parser.get_photos_sync_interval(config=config) < 0
            if "photos" in config
            else True
        ):
            break
        sleep(sleep_for)
