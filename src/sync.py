import datetime
from time import sleep
import os

from icloudpy import ICloudPyService, utils, exceptions
from src import (
    DEFAULT_COOKIE_DIRECTORY,
    config_parser,
    notify,
    LOGGER,
    read_config,
    ENV_ICLOUD_PASSWORD_KEY,
)
from src import sync_drive, sync_photos


def sync():
    last_send = None
    enable_sync_drive = True
    enable_sync_photos = True
    drive_sync_interval = 0
    photos_sync_interval = 0
    sleep_for = 10
    while True:
        config = read_config()
        username = config_parser.get_username(config=config)
        if username:
            try:
                if ENV_ICLOUD_PASSWORD_KEY in os.environ:
                    password = os.environ.get(ENV_ICLOUD_PASSWORD_KEY)
                    utils.store_password_in_keyring(
                        username=username, password=password
                    )
                else:
                    password = utils.get_password_from_keyring(username=username)
                api = ICloudPyService(
                    apple_id=username,
                    password=password,
                    cookie_directory=DEFAULT_COOKIE_DIRECTORY,
                )
                if not api.requires_2sa:
                    if "drive" in config and enable_sync_drive:
                        sync_drive.sync_drive(config=config, drive=api.drive)
                        drive_sync_interval = config_parser.get_drive_sync_interval(
                            config=config
                        )
                    if "photos" in config and enable_sync_photos:
                        sync_photos.sync_photos(config=config, photos=api.photos)
                        photos_sync_interval = config_parser.get_photos_sync_interval(
                            config=config
                        )
                    if "drive" not in config and "photos" not in config:
                        LOGGER.warning(
                            "Nothing to sync. Please add drive: and/or photos: section in config.yaml file."
                        )
                else:
                    LOGGER.error("Error: 2FA is required. Please log in.")
                    # Retry again
                    sleep_for = config_parser.get_retry_login_interval(config=config)
                    next_sync = (
                        datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)
                    ).strftime("%c")
                    LOGGER.info("Retrying login at %s ...", next_sync)
                    last_send = notify.send(config, last_send)
                    sleep(sleep_for)
                    continue
            except exceptions.ICloudPyNoStoredPasswordAvailableException:
                LOGGER.error(
                    "Password is not stored in keyring. Please save the password in keyring."
                )
                sleep_for = config_parser.get_retry_login_interval(config=config)
                next_sync = (
                    datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)
                ).strftime("%c")
                LOGGER.info("Retrying login at %s ...", next_sync)
                last_send = notify.send(config, last_send)
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
        elif (
            "drive" in config
            and "photos" in config
            and drive_sync_interval <= photos_sync_interval
        ):
            sleep_for = photos_sync_interval - drive_sync_interval
            photos_sync_interval -= drive_sync_interval
            enable_sync_drive = True
            enable_sync_photos = False
        else:
            sleep_for = drive_sync_interval - photos_sync_interval
            drive_sync_interval -= photos_sync_interval
            enable_sync_drive = False
            enable_sync_photos = True
        next_sync = (
            datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)
        ).strftime("%c")
        LOGGER.info("Resyncing at %s ...", next_sync)
        if (
            config_parser.get_drive_sync_interval(config=config) < 0
            if "drive" in config
            else True and config_parser.get_photos_sync_interval(config=config) < 0
            if "photos" in config
            else True
        ):
            break
        sleep(sleep_for)
