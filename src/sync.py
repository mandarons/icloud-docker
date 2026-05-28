"""Sync module."""

__author__ = "Mandar Patil <mandarons@pm.me>"
import datetime
import os
from time import sleep

from icloudpy import ICloudPyService, exceptions, utils

from src import (
    DEFAULT_CONFIG_FILE_PATH,
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
    cookie_directory: str | None = None,
    server_region: str = "global",
) -> ICloudPyService:
    """
    Create and return an iCloud API client instance.

    Args:
        username: iCloud username/Apple ID
        password: iCloud password
        cookie_directory: Directory to store authentication cookies.
            When ``None`` (the default), resolved late from
            ``src.DEFAULT_COOKIE_DIRECTORY`` so test fixtures that
            redirect the constant at runtime take effect — the previous
            ``= DEFAULT_COOKIE_DIRECTORY`` default-arg capture made the
            constant unmockable post-import.
        server_region: Server region ("china" or "global")

    Returns:
        Configured ICloudPyService instance
    """
    if cookie_directory is None:
        # Read through the src module so monkey-patches of
        # ``src.DEFAULT_COOKIE_DIRECTORY`` (e.g. by tests/conftest.py)
        # are honoured. ``src`` is this function's parent package and
        # already imported; using ``sys.modules`` avoids a per-call
        # ``import src`` and makes the data flow explicit.
        import sys

        cookie_directory = sys.modules["src"].DEFAULT_COOKIE_DIRECTORY
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


def _check_mount_marker(
    destinations: list[str],
    marker_filename: str,
    required: bool,
    service_name: str,
) -> bool:
    """Verify the failsafe marker file is present in every write destination.

    Mirrors boredazfcuk/docker-icloudpd's ``.mounted`` pattern: protects
    against silent bind-mount failures (typo in the host path, missing
    share, wrong permissions) that would otherwise dump iCloud data into
    an empty container-internal directory.

    Takes a list of destinations because a single sync may write to
    multiple bind-mounted directories — e.g. Photos with
    ``library_destinations`` mapping the personal library to
    ``/photos/personal`` and the shared library to ``/photos/shared``,
    each potentially a separate mount. The marker is required in EACH
    write destination because any one of them could be the failed mount.

    Returns True when it is safe to proceed (marker not required, or
    marker required and present in every destination). Returns False when
    the marker is required and is missing from at least one destination —
    in which case the caller should skip this sync cycle without
    advancing the countdown so the next interval re-checks. Every
    missing-marker failure is logged so the user can fix all of them in
    one pass rather than discovering them one cycle at a time.

    Args:
        destinations: List of sync destination directories to check. Each
            directory is checked independently. An empty list returns
            True (nothing to check).
        marker_filename: Filename to look for inside each destination
            (e.g. ``.mounted``).
        required: Whether the marker is required at all. When False this
            is a no-op that always returns True.
        service_name: Human-readable label used in the error log
            (``Drive`` / ``Photos``).

    Returns:
        True if it is safe to proceed; False to skip this sync cycle.
    """
    if not required:
        return True
    all_present = True
    for destination_path in destinations:
        marker_path = os.path.join(destination_path, marker_filename)
        if not os.path.isfile(marker_path):
            LOGGER.error(
                f"{service_name} mount marker missing: {marker_path} not found — "
                f"refusing to sync. Create the marker file (`touch {marker_path}`) "
                f"after confirming the destination is correctly mounted, then the "
                f"next sync cycle will proceed.",
            )
            all_present = False
    return all_present


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

        # Mount-marker failsafe (see _check_mount_marker). Skip this cycle
        # without advancing the countdown so the next interval re-checks
        # once the user fixes the mount + touches the marker file.
        if not _check_mount_marker(
            destinations=[destination_path],
            marker_filename=config_parser.get_mount_marker_filename(config=config),
            required=config_parser.get_drive_require_mount_marker(config=config),
            service_name="Drive",
        ):
            return None

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

        # Handle case where sync_drive returns None (e.g., in tests)
        if files_after is not None:
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

        # Mount-marker failsafe (see _check_mount_marker). Skip this cycle
        # without advancing the countdown so the next interval re-checks
        # once the user fixes the mount + touches the marker file.
        #
        # If ``photos.library_destinations`` is configured, EACH mapped
        # subdir is a separate write target (often a separate bind mount
        # — that's the whole reason users map libraries to subdirs).
        # Check the marker in each: the failed-mount one could be any of
        # them. Root is still checked because libraries with no explicit
        # mapping fall through to it via ``_library_destination``.
        # Read defensively so this PR is independent of the
        # library_destinations PR being merged first.
        photos_cfg = config.get("photos") if isinstance(config, dict) else None
        library_destinations = photos_cfg.get("library_destinations") if isinstance(photos_cfg, dict) else None
        marker_destinations = [destination_path]
        if isinstance(library_destinations, dict):
            for subdir in library_destinations.values():
                if not isinstance(subdir, str) or not subdir:
                    continue
                marker_destinations.append(os.path.join(destination_path, subdir))
        if not _check_mount_marker(
            destinations=marker_destinations,
            marker_filename=config_parser.get_mount_marker_filename(config=config),
            required=config_parser.get_photos_require_mount_marker(config=config),
            service_name="Photos",
        ):
            return None

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
        sync_result = sync_photos.sync_photos(config=config, photos=api.photos)
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
        use_hardlinks = config_parser.get_photos_use_hardlinks(config=config, log_messages=False)
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

        # Track failed downloads so notifications reflect errors
        if isinstance(sync_result, tuple):
            _, failed_downloads = sync_result
            if failed_downloads > 0:
                stats.errors.append(f"{failed_downloads} photo download(s) failed")

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


def _send_usage_statistics(config, summary: SyncSummary) -> None:
    """Send anonymized usage statistics.

    Args:
        config: Configuration dictionary
        summary: Sync summary with statistics
    """

    # Create anonymized usage data
    usage_data = {
        "sync_duration": (
            (summary.sync_end_time - summary.sync_start_time).total_seconds() if summary.sync_end_time else 0
        ),
        "has_drive_activity": bool(summary.drive_stats and summary.drive_stats.has_activity()),
        "has_photos_activity": bool(summary.photo_stats and summary.photo_stats.has_activity()),
        "has_errors": summary.has_errors(),
        "timestamp": (summary.sync_end_time.isoformat() if summary.sync_end_time else None),
    }

    # Add aggregated statistics (no personal data)
    if summary.drive_stats:
        usage_data["drive"] = {
            "files_count": summary.drive_stats.files_downloaded,
            "bytes_count": summary.drive_stats.bytes_downloaded,
            "has_errors": summary.drive_stats.has_errors(),
        }

    if summary.photo_stats:
        usage_data["photos"] = {
            "photos_count": summary.photo_stats.photos_downloaded,
            "bytes_count": summary.photo_stats.bytes_downloaded,
            "hardlinks_count": summary.photo_stats.photos_hardlinked,
            "has_errors": summary.photo_stats.has_errors(),
        }

    # Send to usage tracking
    alive(config=config, data=usage_data)


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
        # Special case: if both timers are equal and large (> 10 seconds), wait for the full interval
        # This fixes the bug where equal large intervals cause immediate re-sync
        if sync_state.drive_time_remaining == sync_state.photos_time_remaining and sync_state.drive_time_remaining > 10:
            sleep_for = sync_state.drive_time_remaining
            sync_state.enable_sync_drive = True
            sync_state.enable_sync_photos = True
        else:
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

                    # Send usage statistics (anonymized summary data)
                    try:
                        _send_usage_statistics(config, summary)
                    except Exception as e:
                        LOGGER.debug(f"Failed to send usage statistics: {e!s}")

                    # Send sync summary notification if configured
                    # Only send notification when both enabled services have synced in this cycle
                    # Gracefully handle notification failures to not break sync
                    has_drive_config = config and "drive" in config
                    has_photos_config = config and "photos" in config

                    should_send_notification = False
                    if has_drive_config and has_photos_config:
                        # Both services configured - send notification only when both have synced
                        should_send_notification = drive_stats is not None and photos_stats is not None
                    elif has_drive_config and not has_photos_config:
                        # Only drive configured - send when drive synced
                        should_send_notification = drive_stats is not None
                    elif has_photos_config and not has_drive_config:
                        # Only photos configured - send when photos synced
                        should_send_notification = photos_stats is not None

                    if should_send_notification:
                        try:
                            notify.send_sync_summary(config=config, summary=summary)
                        except Exception as e:
                            LOGGER.debug(f"Failed to send sync summary notification: {e!s}")

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
