__author__ = "Mandar Patil (mandarons@pm.me)"

import os
from src import (
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
            "username is missing in %s. Please set the username.",
            config_path_to_string(config_path),
        )
    else:
        username = get_config_value(config=config, config_path=config_path)
        username = username.strip()
        if len(username) == 0:
            username = None
            LOGGER.error("username is empty in %s", config_path_to_string(config_path))
    return username


def get_drive_sync_interval(config):
    sync_interval = DEFAULT_SYNC_INTERVAL_SEC
    config_path = ["drive", "sync_interval"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            "sync_interval is not found in %s. Using default sync_interval: %s seconds ...",
            config_path_to_string(config_path=config_path),
            sync_interval,
        )
    else:
        sync_interval = get_config_value(config=config, config_path=config_path)
        LOGGER.info("Syncing drive every %s seconds.", sync_interval)
    return sync_interval


def get_photos_sync_interval(config):
    sync_interval = DEFAULT_SYNC_INTERVAL_SEC
    config_path = ["photos", "sync_interval"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            "sync_interval is not found in %s. Using default sync_interval: %s seconds ...",
            config_path_to_string(config_path=config_path),
            sync_interval,
        )
    else:
        sync_interval = get_config_value(config=config, config_path=config_path)
        LOGGER.info("Syncing photos every %s seconds.", sync_interval)
    return sync_interval


def prepare_root_destination(config):
    LOGGER.debug("Checking root destination ...")
    root_destination = DEFAULT_ROOT_DESTINATION
    config_path = ["app", "root"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            "Warning: root destination is missing in %s. Using default root destination: %s",
            config_path_to_string(config_path),
            root_destination,
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


def get_smtp_password(config):
    password = None
    config_path = ["app", "smtp", "password"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            "Warning: password is not found in %s", config_path_to_string(config_path)
        )
    else:
        password = get_config_value(config=config, config_path=config_path)
    return password


def get_smtp_host(config):
    host = None
    config_path = ["app", "smtp", "host"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            "Warning: host is not found in %s", config_path_to_string(config_path)
        )
    else:
        host = get_config_value(config=config, config_path=config_path)
    return host


def get_smtp_port(config):
    port = None
    config_path = ["app", "smtp", "port"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            "Warning: port is not found in %s", config_path_to_string(config_path)
        )
    else:
        port = get_config_value(config=config, config_path=config_path)
    return port


def get_smtp_no_tls(config):
    no_tls = False
    config_path = ["app", "smtp", "no_tls"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            "Warning: no_tls is not found in %s", config_path_to_string(config_path)
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
            "Warning: destination is missing in %s. Using default drive destination: %s.",
            config_path_to_string(config_path),
            drive_destination,
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
            "Warning: remove_obsolete is not found in %s. Not removing the obsolete files and folders.",
            config_path_to_string(config_path),
        )
    else:
        drive_remove_obsolete = get_config_value(config=config, config_path=config_path)
        LOGGER.info(
            "%semoving obsolete files and folders ...",
            "R" if drive_remove_obsolete else "Not R",
        )
    return drive_remove_obsolete


def prepare_photos_destination(config):
    LOGGER.info("Checking photos destination ...")
    config_path = ["photos", "destination"]
    photos_destination = DEFAULT_PHOTOS_DESTINATION
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            "Warning: destination is missing in %s. Using default photos destination: %s",
            photos_destination,
            config_path_to_string(config_path),
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
            "Warning: remove_obsolete is not found in %s. Not removing the obsolete photos.",
            config_path_to_string(config_path),
        )
    else:
        photos_remove_obsolete = get_config_value(
            config=config, config_path=config_path
        )
        LOGGER.info(
            "%semoving obsolete photos ...", "R" if photos_remove_obsolete else "Not R"
        )
    return photos_remove_obsolete


def get_photos_filters(config):
    photos_filters = {"albums": None, "file_sizes": ["original"]}
    valid_file_sizes = ["original", "medium", "thumb"]
    config_path = ["photos", "filters"]
    if not traverse_config_path(config=config, config_path=config_path):
        LOGGER.warning(
            "%s not found. Downloading all albums with original size ...",
            config_path_to_string(config_path=config_path),
        )
    else:
        config_path.append("albums")
        if (
            not traverse_config_path(config=config, config_path=config_path)
            or not get_config_value(config=config, config_path=config_path)
            or len(get_config_value(config=config, config_path=config_path)) == 0
        ):
            LOGGER.warning(
                "%s not found. Downloading all albums ...",
                config_path_to_string(config_path=config_path),
            )
        else:
            photos_filters["albums"] = get_config_value(
                config=config, config_path=config_path
            )
        config_path[2] = "file_sizes"
        if not traverse_config_path(config=config, config_path=config_path):
            LOGGER.warning(
                "%s not found. Downloading original size photos ...",
                config_path_to_string(config_path=config_path),
            )
        else:
            file_sizes = get_config_value(config=config, config_path=config_path)
            for file_size in file_sizes:
                if not file_size in valid_file_sizes:
                    LOGGER.warning(
                        "Skipping the invalid file size %s, valid file sizes are %s ",
                        file_size,
                        ",".join(valid_file_sizes),
                    )
                    file_sizes.remove(file_size)
                    if len(file_sizes) == 0:
                        file_sizes = ["original"]
            photos_filters["file_sizes"] = file_sizes
    return photos_filters
