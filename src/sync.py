import datetime
import time
from pyicloud import PyiCloudService, utils, exceptions
from src import sync_drive, sync_photos, config_parser, notify


def sync():
    last_send = None
    while True:
        config = config_parser.read_config()
        verbose = config_parser.get_verbose(config=config)
        username = config_parser.get_username(config=config)
        if username:
            try:
                api = PyiCloudService(
                    apple_id=username,
                    password=utils.get_password_from_keyring(username=username),
                )
                if not api.requires_2sa:
                    sync_drive.sync_drive(
                        config=config,
                        drive=api.drive,
                        verbose=verbose,
                    )
                    sync_photos.sync_photos(
                        config=config, photos=api.photos, verbose=verbose
                    )
                else:
                    print("Error: 2FA is required. Please log in.")
                    last_send = notify.send(config, last_send)
            except exceptions.PyiCloudNoStoredPasswordAvailableException:

                print(
                    "password is not stored in keyring. Please save the password in keyring."
                )
        sleep_for = config_parser.get_sync_interval(config=config)
        next_sync = (
            datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)
        ).strftime("%c")
        print(f"Resyncing at {next_sync} ...")
        if sleep_for < 0:
            break
        time.sleep(sleep_for)
