__author__ = "Mandar Patil (mandarons@pm.me)"

import os
from src import (
    DEFAULT_RETRY_LOGIN_INTERVAL_SEC,
    LOGGER,
    DEFAULT_ROOT_DESTINATION,
    DEFAULT_DRIVE_DESTINATION,
    DEFAULT_SYNC_INTERVAL_SEC,
    DEFAULT_PHOTOS_DESTINATION,
)


def config_path_to_string(config_path):
    return " > ".join(config_path)


def traverse_config_path(config, config_path: list[str]) -> bool:
    if len(config_path) == 0:
        return True
    if not (config and config_path[0] in config):
        return False
    return traverse_config_path(config[config_path[0]], config_path=config_path[1:])


def get_config_value(config, config_path):
    if len(config_path) == 1:
        return config[config_path[0]]
    return get_config_value(config=config[config_path[0]], config_path=config_path[1:])


def get_username(config):
    username = None
    config_path = ["app", "credentials", "username"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.error(
            f"username is missing in {config_path_to_string(config_path)}. Please set the username."
        )
    else:
        username = get_config_value(config=config, config_path=config_path)
        username = username.strip()
        if len(username) == 0:
            username = None
            LOGGER.error(f"username is empty in {config_path_to_string(config_path)}.")
    return username


def get_retry_login_interval(config):
    retry_login_interval = DEFAULT_RETRY_LOGIN_INTERVAL_SEC
    config_path = ["app", "credentials", "retry_login_interval"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"retry_login_interval not found in {config_path_to_string(config_path=config_path)}."
            + f" Using default {retry_login_interval} seconds ..."
        )
    else:
        retry_login_interval = get_config_value(config=config, config_path=config_path)
        LOGGER.info(f"Retrying login every {retry_login_interval} seconds.")
    return retry_login_interval


def get_drive_sync_interval(config):
    sync_interval = DEFAULT_SYNC_INTERVAL_SEC
    config_path = ["drive", "sync_interval"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"sync_interval is not found in {config_path_to_string(config_path=config_path)}."
            + f" Using default sync_interval: {sync_interval} seconds ..."
        )
    else:
        sync_interval = get_config_value(config=config, config_path=config_path)
        LOGGER.info(f"Syncing drive every {sync_interval} seconds.")
    return sync_interval


def get_photos_sync_interval(config):
    sync_interval = DEFAULT_SYNC_INTERVAL_SEC
    config_path = ["photos", "sync_interval"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"sync_interval is not found in {config_path_to_string(config_path=config_path)}."
            + f" Using default sync_interval: {sync_interval} seconds ..."
        )
    else:
        sync_interval = get_config_value(config=config, config_path=config_path)
        LOGGER.info(f"Syncing photos every {sync_interval} seconds.")
    return sync_interval


def prepare_root_destination(config):
    LOGGER.debug("Checking root destination ...")
    root_destination = DEFAULT_ROOT_DESTINATION
    config_path = ["app", "root"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"Warning: root destination is missing in {config_path_to_string(config_path)}."
            + f" Using default root destination: {root_destination}",
        )
    else:
        root_destination = get_config_value(config=config, config_path=config_path)
    root_destination_path = os.path.abspath(root_destination)
    os.makedirs(root_destination_path, exist_ok=True)
    return root_destination_path


def get_smtp_email(config):
    email = None
    config_path = ["app", "smtp", "email"]
    if traverse_config_path(config=config, config_path=config_path):
        email = get_config_value(config=config, config_path=config_path)
    return email


def get_smtp_to_email(config):
    to_email = None
    config_path = ["app", "smtp", "to"]
    if traverse_config_path(config=config, config_path=config_path):
        to_email = get_config_value(config=config, config_path=config_path)
    else:
        to_email = get_smtp_email(config=config)
    return to_email


def get_smtp_password(config):
    password = None
    config_path = ["app", "smtp", "password"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"Warning: password is not found in {config_path_to_string(config_path)}"
        )
    else:
        password = get_config_value(config=config, config_path=config_path)
    return password


def get_smtp_host(config):
    host = None
    config_path = ["app", "smtp", "host"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"Warning: host is not found in {config_path_to_string(config_path)}"
        )
    else:
        host = get_config_value(config=config, config_path=config_path)
    return host


def get_smtp_port(config):
    port = None
    config_path = ["app", "smtp", "port"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"Warning: port is not found in {config_path_to_string(config_path)}"
        )
    else:
        port = get_config_value(config=config, config_path=config_path)
    return port


def get_smtp_no_tls(config):
    no_tls = False
    config_path = ["app", "smtp", "no_tls"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"Warning: no_tls is not found in {config_path_to_string(config_path)}"
        )
    else:
        no_tls = get_config_value(config=config, config_path=config_path)
    return no_tls


def prepare_drive_destination(config):
    LOGGER.debug("Checking drive destination ...")
    config_path = ["drive", "destination"]
    drive_destination = DEFAULT_DRIVE_DESTINATION
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"Warning: destination is missing in {config_path_to_string(config_path)}."
            + f" Using default drive destination: {drive_destination}."
        )
    else:
        drive_destination = get_config_value(config=config, config_path=config_path)
    drive_destination_path = os.path.abspath(
        os.path.join(prepare_root_destination(config=config), drive_destination)
    )
    os.makedirs(drive_destination_path, exist_ok=True)
    return drive_destination_path


def get_drive_remove_obsolete(config):
    drive_remove_obsolete = False
    config_path = ["drive", "remove_obsolete"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"Warning: remove_obsolete is not found in {config_path_to_string(config_path)}."
            + " Not removing the obsolete files and folders."
        )
    else:
        drive_remove_obsolete = get_config_value(config=config, config_path=config_path)
        LOGGER.debug(
            f"{'R' if drive_remove_obsolete else 'Not R'}emoving obsolete files and folders ..."
        )
    return drive_remove_obsolete


def prepare_photos_destination(config):
    LOGGER.debug("Checking photos destination ...")
    config_path = ["photos", "destination"]
    photos_destination = DEFAULT_PHOTOS_DESTINATION
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"Warning: destination is missing in {photos_destination}."
            + f" Using default photos destination: {config_path_to_string(config_path)}"
        )
    else:
        photos_destination = get_config_value(config=config, config_path=config_path)
    photos_destination_path = os.path.abspath(
        os.path.join(prepare_root_destination(config=config), photos_destination)
    )
    os.makedirs(photos_destination_path, exist_ok=True)
    return photos_destination_path


def get_photos_remove_obsolete(config):
    photos_remove_obsolete = False
    config_path = ["photos", "remove_obsolete"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"Warning: remove_obsolete is not found in {config_path_to_string(config_path)}."
            + " Not removing the obsolete photos."
        )
    else:
        photos_remove_obsolete = get_config_value(
            config=config, config_path=config_path
        )
        LOGGER.debug(
            f"{'R' if photos_remove_obsolete else 'Not R'}emoving obsolete photos ..."
        )
    return photos_remove_obsolete


def get_photos_filters(config):
    photos_filters = {"albums": None, "file_sizes": ["original"]}
    valid_file_sizes = ["original", "medium", "thumb"]
    config_path = ["photos", "filters"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"{config_path_to_string(config_path=config_path)} not found. Downloading all albums with original size ..."
        )
    else:
        config_path.append("albums")
        if (
            not traverse_config_path(config=config, config_path=config_path)
            or not get_config_value(config=config, config_path=config_path)
            or len(get_config_value(config=config, config_path=config_path)) == 0
        ):
            LOGGER.warning(
                f"{config_path_to_string(config_path=config_path)} not found. Downloading all albums ..."
            )
        else:
            photos_filters["albums"] = get_config_value(
                config=config, config_path=config_path
            )
        config_path[2] = "file_sizes"
        if not traverse_config_path(config=config, config_path=config_path):
            LOGGER.warning(
                f"{config_path_to_string(config_path=config_path)} not found. Downloading original size photos ..."
            )
        else:
            file_sizes = get_config_value(config=config, config_path=config_path)
            for file_size in file_sizes:
                if not file_size in valid_file_sizes:
                    LOGGER.warning(
                        f"Skipping the invalid file size {file_size}, "
                        + f"valid file sizes are {','.join(valid_file_sizes)}."
                    )
                    file_sizes.remove(file_size)
                    if len(file_sizes) == 0:
                        file_sizes = ["original"]
            photos_filters["file_sizes"] = file_sizes
    return photos_filters


def get_region(config):
    region = "global"
    config_path = ["app", "region"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            f"{config_path_to_string(config_path=config_path)} not found. Using default value - global ..."
        )
    else:
        region = get_config_value(config=config, config_path=config_path)
        if region not in ["global", "china"]:
            LOGGER.error(
                f"{config_path_to_string(config_path=config_path)} is invalid. \
                            Valid values are - global or china. Using default value - global ..."
            )
            region = "global"

    return region
