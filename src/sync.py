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
    configure_icloudpy_logging,
    get_logger,
    notify,
    read_config,
    sync_drive,
    sync_photos,
)
from src.sync_stats import SyncSummary
from src.usage import alive

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()


def get_api_instance(
    username: str,
    password: str,
    cookie_directory: str = DEFAULT_COOKIE_DIRECTORY,
    server_region: str = "global",
) -> ICloudPyService:
    """
    Create and return an iCloud API client instance.

    Args:
        username: iCloud username/Apple ID
        password: iCloud password
        cookie_directory: Directory to store authentication cookies
        server_region: Server region ("china" or "global")

    Returns:
        Configured ICloudPyService instance
    """
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


class SyncState:
    """
    Maintains synchronization state for drive and photos.

    This class encapsulates the countdown timers and sync flags to avoid
    passing multiple variables between functions.
    """

    def __init__(self):
        """Initialize sync state with default values."""
        self.drive_time_remaining = 0
        self.photos_time_remaining = 0
        self.enable_sync_drive = True
        self.enable_sync_photos = True
        self.last_send = None


def _load_configuration():
    """
    Load configuration from file or environment.

    Returns:
        Configuration dictionary
    """
    config_path = os.environ.get(ENV_CONFIG_FILE_PATH_KEY, DEFAULT_CONFIG_FILE_PATH)
    return read_config(config_path=config_path)


def _extract_sync_intervals(config, log_messages: bool = False):
    """
    Extract drive and photos sync intervals from configuration.

    Args:
        config: Configuration dictionary
        log_messages: Whether to log informational messages (default: False for loop usage)

    Returns:
        tuple: (drive_sync_interval, photos_sync_interval)
    """
    drive_sync_interval = 0
    photos_sync_interval = 0

    if config and "drive" in config:
        drive_sync_interval = config_parser.get_drive_sync_interval(config=config, log_messages=log_messages)
    if config and "photos" in config:
        photos_sync_interval = config_parser.get_photos_sync_interval(config=config, log_messages=log_messages)

    return drive_sync_interval, photos_sync_interval


def _retrieve_password(username: str):
    """
    Retrieve password from environment or keyring.

    Args:
        username: iCloud username

    Returns:
        Password string or None if not found

    Raises:
        ICloudPyNoStoredPasswordAvailableException: If password not available
    """
    if ENV_ICLOUD_PASSWORD_KEY in os.environ:
        password = os.environ.get(ENV_ICLOUD_PASSWORD_KEY)
        utils.store_password_in_keyring(username=username, password=password)
        return password
    else:
        return utils.get_password_from_keyring(username=username)


def _authenticate_and_get_api(config, username: str):
    """
    Authenticate user and return iCloud API instance.

    Args:
        config: Configuration dictionary
        username: iCloud username

    Returns:
        ICloudPyService instance

    Raises:
        ICloudPyNoStoredPasswordAvailableException: If password not available
    """
    server_region = config_parser.get_region(config=config)
    password = _retrieve_password(username)
    return get_api_instance(username=username, password=password, server_region=server_region)


def _perform_drive_sync(config, api, sync_state: SyncState, drive_sync_interval: int):
    """
    Execute drive synchronization if enabled.

    Args:
        config: Configuration dictionary
        api: iCloud API instance
        sync_state: Current sync state
        drive_sync_interval: Drive sync interval in seconds

    Returns:
        DriveStats object if sync was performed, None otherwise
    """
    if config and "drive" in config and sync_state.enable_sync_drive:
        import time

        from src.sync_stats import DriveStats

        start_time = time.time()
        stats = DriveStats()

        destination_path = config_parser.prepare_drive_destination(config=config)

        # Count files before sync
        files_before = set()
        if os.path.exists(destination_path):
            try:
                for root, _dirs, file_list in os.walk(destination_path):
                    for file in file_list:
                        files_before.add(os.path.join(root, file))
            except Exception:
                pass

        LOGGER.info("Syncing drive...")
        files_after = sync_drive.sync_drive(config=config, drive=api.drive)
        LOGGER.info("Drive synced")

        # Calculate statistics
        stats.duration_seconds = time.time() - start_time

        # Count newly downloaded files
        new_files = files_after - files_before
        stats.files_downloaded = len(new_files)

        # Count skipped files
        stats.files_skipped = len(files_before & files_after)

        # Count removed files
        if config_parser.get_drive_remove_obsolete(config=config):
            stats.files_removed = len(files_before - files_after)

        # Calculate bytes downloaded
        try:
            for file_path in new_files:
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    stats.bytes_downloaded += os.path.getsize(file_path)
        except Exception:
            pass

        # Reset countdown timer to the configured interval
        sync_state.drive_time_remaining = drive_sync_interval
        return stats
    return None


def _perform_photos_sync(config, api, sync_state: SyncState, photos_sync_interval: int):
    """
    Execute photos synchronization if enabled.

    Args:
        config: Configuration dictionary
        api: iCloud API instance
        sync_state: Current sync state
        photos_sync_interval: Photos sync interval in seconds

    Returns:
        PhotoStats object if sync was performed, None otherwise
    """
    if config and "photos" in config and sync_state.enable_sync_photos:
        import time

        from src.sync_stats import PhotoStats

        start_time = time.time()
        stats = PhotoStats()

        destination_path = config_parser.prepare_photos_destination(config=config)

        # Count files before sync
        files_before = set()
        if os.path.exists(destination_path):
            try:
                for root, _dirs, file_list in os.walk(destination_path):
                    for file in file_list:
                        files_before.add(os.path.join(root, file))
            except Exception:
                pass

        LOGGER.info("Syncing photos...")
        sync_photos.sync_photos(config=config, photos=api.photos)
        LOGGER.info("Photos synced")

        # Count files after sync
        files_after = set()
        if os.path.exists(destination_path):
            try:
                for root, _dirs, file_list in os.walk(destination_path):
                    for file in file_list:
                        files_after.add(os.path.join(root, file))
            except Exception:
                pass

        # Calculate statistics
        stats.duration_seconds = time.time() - start_time

        # Count newly downloaded files
        new_files = files_after - files_before
        stats.photos_downloaded = len(new_files)

        # Estimate hardlinked photos (approximate)
        use_hardlinks = config_parser.get_photos_use_hardlinks(config=config)
        if use_hardlinks:
            stats.photos_hardlinked = max(0, len(files_after) - len(files_before) - stats.photos_downloaded)

        # Count skipped photos
        stats.photos_skipped = len(files_before & files_after)

        # Calculate bytes downloaded
        try:
            for file_path in new_files:
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    stats.bytes_downloaded += os.path.getsize(file_path)

            # Estimate bytes saved by hardlinks
            if use_hardlinks and stats.photos_hardlinked > 0:
                for file_path in files_after:
                    if file_path not in new_files and os.path.isfile(file_path):
                        stats.bytes_saved_by_hardlinks += os.path.getsize(file_path)
        except Exception:
            pass

        # Get list of synced albums (simple approximation based on directories)
        try:
            for item in os.listdir(destination_path):
                item_path = os.path.join(destination_path, item)
                if os.path.isdir(item_path):
                    stats.albums_synced.append(item)
        except Exception:
            pass

        # Reset countdown timer to the configured interval
        sync_state.photos_time_remaining = photos_sync_interval
        return stats
    return None


def _check_services_configured(config):
    """
    Check if any sync services are configured.

    Args:
        config: Configuration dictionary

    Returns:
        bool: True if at least one service is configured
    """

    return "drive" in config or "photos" in config


def _handle_2fa_required(config, username: str, sync_state: SyncState):
    """
    Handle 2FA authentication requirement.

    Args:
        config: Configuration dictionary
        username: iCloud username
        sync_state: Current sync state

    Returns:
        bool: True if should continue (retry), False if should exit
    """
    LOGGER.error("Error: 2FA is required. Please log in.")
    sleep_for = config_parser.get_retry_login_interval(config=config)

    if sleep_for < 0:
        LOGGER.info("retry_login_interval is < 0, exiting ...")
        return False

    _log_retry_time(sleep_for)
    server_region = config_parser.get_region(config=config)
    sync_state.last_send = notify.send(
        config=config,
        username=username,
        last_send=sync_state.last_send,
        region=server_region,
    )
    sleep(sleep_for)
    return True


def _handle_password_error(config, username: str, sync_state: SyncState):
    """
    Handle password not available error.

    Args:
        config: Configuration dictionary
        username: iCloud username
        sync_state: Current sync state

    Returns:
        bool: True if should continue (retry), False if should exit
    """
    LOGGER.error("Password is not stored in keyring. Please save the password in keyring.")
    sleep_for = config_parser.get_retry_login_interval(config=config)

    if sleep_for < 0:
        LOGGER.info("retry_login_interval is < 0, exiting ...")
        return False

    _log_retry_time(sleep_for)
    server_region = config_parser.get_region(config=config)
    sync_state.last_send = notify.send(
        config=config,
        username=username,
        last_send=sync_state.last_send,
        region=server_region,
    )
    sleep(sleep_for)
    return True


def _log_retry_time(sleep_for: int):
    """
    Log the next retry time.

    Args:
        sleep_for: Sleep duration in seconds
    """
    next_sync = (datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)).strftime("%c")
    LOGGER.info(f"Retrying login at {next_sync} ...")


def _calculate_next_sync_schedule(config, sync_state: SyncState):
    """
    Calculate next sync schedule and update sync state.

    This function implements the adaptive scheduling algorithm that determines
    which service should sync next based on countdown timers.

    Args:
        config: Configuration dictionary
        sync_state: Current sync state

    Returns:
        int: Sleep duration in seconds
    """
    has_drive = config and "drive" in config
    has_photos = config and "photos" in config

    if not has_drive and has_photos:
        sleep_for = sync_state.photos_time_remaining
        sync_state.enable_sync_drive = False
        sync_state.enable_sync_photos = True
    elif has_drive and not has_photos:
        sleep_for = sync_state.drive_time_remaining
        sync_state.enable_sync_drive = True
        sync_state.enable_sync_photos = False
    elif has_drive and has_photos and sync_state.drive_time_remaining <= sync_state.photos_time_remaining:
        sleep_for = sync_state.photos_time_remaining - sync_state.drive_time_remaining
        sync_state.photos_time_remaining -= sync_state.drive_time_remaining
        sync_state.enable_sync_drive = True
        sync_state.enable_sync_photos = False
    else:
        sleep_for = sync_state.drive_time_remaining - sync_state.photos_time_remaining
        sync_state.drive_time_remaining -= sync_state.photos_time_remaining
        sync_state.enable_sync_drive = False
        sync_state.enable_sync_photos = True

    return sleep_for


def _log_next_sync_time(sleep_for: int):
    """
    Log the next scheduled sync time.

    Args:
        sleep_for: Sleep duration in seconds
    """
    next_sync = (datetime.datetime.now() + datetime.timedelta(seconds=sleep_for)).strftime("%c")
    LOGGER.info(f"Resyncing at {next_sync} ...")


def _log_sync_intervals_at_startup(config):
    """
    Log sync intervals once at startup.

    Args:
        config: Configuration dictionary
    """
    if config and "drive" in config:
        config_parser.get_drive_sync_interval(config=config, log_messages=True)
    if config and "photos" in config:
        config_parser.get_photos_sync_interval(config=config, log_messages=True)


def _should_exit_oneshot_mode(config):
    """
    Check if should exit in oneshot mode.

    Oneshot mode exits when ALL configured sync intervals are negative.

    Args:
        config: Configuration dictionary

    Returns:
        bool: True if should exit
    """

    should_exit_drive = ("drive" not in config) or (
        config_parser.get_drive_sync_interval(config=config, log_messages=False) < 0
    )
    should_exit_photos = ("photos" not in config) or (
        config_parser.get_photos_sync_interval(config=config, log_messages=False) < 0
    )

    return should_exit_drive and should_exit_photos


def sync():
    """
    Main synchronization loop.

    Orchestrates the entire sync process by delegating specific responsibilities
    to focused helper functions. This function coordinates the high-level flow
    while each helper handles a single concern.
    """
    sync_state = SyncState()
    startup_logged = False

    while True:
        config = _load_configuration()
        alive(config=config)

        # Log sync intervals once at startup
        if not startup_logged:
            _log_sync_intervals_at_startup(config)
            startup_logged = True

        drive_sync_interval, photos_sync_interval = _extract_sync_intervals(config, log_messages=False)
        username = config_parser.get_username(config=config) if config else None

        if username:
            try:
                api = _authenticate_and_get_api(config, username)

                if not api.requires_2sa:
                    # Create summary for this sync cycle
                    summary = SyncSummary()

                    # Perform syncs and collect statistics
                    drive_stats = _perform_drive_sync(config, api, sync_state, drive_sync_interval)
                    photos_stats = _perform_photos_sync(config, api, sync_state, photos_sync_interval)

                    # Populate summary with statistics
                    summary.drive_stats = drive_stats
                    summary.photo_stats = photos_stats
                    summary.sync_end_time = datetime.datetime.now()

                    # Send sync summary notification if configured
                    if drive_stats or photos_stats:
                        notify.send_sync_summary(config=config, summary=summary)

                    if not _check_services_configured(config):
                        LOGGER.warning("Nothing to sync. Please add drive: and/or photos: section in config.yaml file.")
                else:
                    if not _handle_2fa_required(config, username, sync_state):
                        break
                    continue

            except exceptions.ICloudPyNoStoredPasswordAvailableException:
                if not _handle_password_error(config, username, sync_state):
                    break
                continue

        sleep_for = _calculate_next_sync_schedule(config, sync_state)
        _log_next_sync_time(sleep_for)

        if _should_exit_oneshot_mode(config):
            LOGGER.info("All configured sync intervals are negative, exiting oneshot mode...")
            break

        sleep(sleep_for)
