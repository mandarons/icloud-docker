"""Sync module."""

__author__ = "Mandar Patil <mandarons@pm.me>"
import datetime
import os
import re
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
        "timestamp": summary.sync_end_time.isoformat() if summary.sync_end_time else None,
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


def _handle_2fa_required(config, username: str, sync_state: SyncState, api=None):
    """
    Handle 2FA authentication requirement.

    Args:
        config: Configuration dictionary
        username: iCloud username
        sync_state: Current sync state
        api: Live ``ICloudPyService`` instance still in its 2FA-required state.
            When provided AND ``app.telegram.listen`` is true, the retry sleep is
            replaced with a Telegram poll: the user replies the auth keyword to
            have Apple push a code to their devices, then replies the 6 digits --
            completing re-authentication from a phone, headless, with no web UI.

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
    # notify.send is throttled (once per 24h) and listen-aware: in listen mode the
    # Telegram channel gets the actionable reply prompt, other channels the standard
    # alert. Throttling here is what prevents a "reply auth" message every retry cycle.
    sync_state.last_send = notify.send(
        config=config,
        username=username,
        last_send=sync_state.last_send,
        region=server_region,
    )
    if api is not None and config_parser.get_telegram_listen_enabled(config=config):
        _wait_for_telegram_code(config=config, api=api, timeout_seconds=sleep_for)
    else:
        sleep(sleep_for)
    return True


def _wait_for_telegram_code(config, api, timeout_seconds: int) -> bool:
    """Drive 2FA over Telegram with a manual, user-initiated trigger.

    The reply prompt itself is sent by ``notify.send`` (throttled); this function
    drains any stale replies, then polls for the user's actions:
      1. On the auth keyword -> ``api.trigger_2fa_push_notification()`` so Apple
         actually pushes a code to the trusted devices. (The headless path
         previously waited for a code it never requested -- this missing trigger
         is the core bug this fixes.)
      2. On a 6-digit reply (spaces/dashes tolerated) -> ``validate_2fa_code``
         + ``trust_session``.

    Returns True once a code validates and trust succeeds within
    ``timeout_seconds``; False on timeout. Best-effort throughout. The Telegram
    ``getUpdates`` offset is held in-memory for the duration of this wait.
    """
    poll_interval = 5
    bot_token = config_parser.get_telegram_bot_token(config=config)
    chat_id = config_parser.get_telegram_chat_id(config=config)
    auth_keyword = config_parser.get_telegram_auth_keyword(config=config)
    if not bot_token or not chat_id:
        LOGGER.warning(
            "Telegram listen enabled but bot_token/chat_id not configured; falling back to plain sleep.",
        )
        sleep(timeout_seconds)
        return False

    # Drain any messages already pending so a stale reply from a previous
    # session does not get acted on; start listening for genuinely new replies.
    _, offset = notify.poll_telegram_for_text(bot_token=bot_token, chat_id=chat_id, offset=0)
    while True:
        _, drained = notify.poll_telegram_for_text(bot_token=bot_token, chat_id=chat_id, offset=offset)
        if drained == offset:
            break
        offset = drained

    LOGGER.info(
        f"Listening on Telegram for '{auth_keyword}' trigger or 6-digit code (timeout {timeout_seconds}s).",
    )
    elapsed = 0
    while elapsed < timeout_seconds:
        chunk = min(poll_interval, timeout_seconds - elapsed)
        sleep(chunk)
        elapsed += chunk
        text, offset = notify.poll_telegram_for_text(
            bot_token=bot_token,
            chat_id=chat_id,
            offset=offset,
        )
        if not text:
            continue
        norm = text.strip().lower()
        if norm == auth_keyword:
            LOGGER.info("Telegram auth trigger received -- requesting 2FA push.")
            try:
                pushed = api.trigger_2fa_push_notification()
            except Exception as e:  # noqa: BLE001
                LOGGER.warning(f"trigger_2fa_push_notification raised: {e!s}")
                pushed = False
            notify.post_message_to_telegram(
                bot_token,
                chat_id,
                (
                    "✅ 2FA code sent to your Apple devices -- reply the 6-digit code here."
                    if pushed
                    else "⚠️ Couldn't request a code (no trusted device, or auth state off). Try again shortly."
                ),
            )
            continue
        code = norm.replace(" ", "").replace("-", "")
        if re.fullmatch(r"\d{6}", code):
            LOGGER.info("Received 6-digit code via Telegram -- validating.")
            try:
                accepted = api.validate_2fa_code(code)
            except Exception as e:  # noqa: BLE001
                LOGGER.warning(f"validate_2fa_code raised: {e!s} -- waiting for another code.")
                continue
            if not accepted:
                notify.post_message_to_telegram(
                    bot_token,
                    chat_id,
                    "❌ Apple rejected that code -- reply a fresh one.",
                )
                LOGGER.warning("Apple rejected the Telegram-supplied code -- waiting for another.")
                continue
            try:
                api.trust_session()
            except Exception as e:  # noqa: BLE001
                LOGGER.warning(f"trust_session raised (non-fatal): {e!s}")
            notify.post_message_to_telegram(
                bot_token,
                chat_id,
                "✅ Re-authenticated. iCloud sync resumed.",
            )
            LOGGER.info("Telegram-driven 2FA succeeded; resuming sync.")
            return True
    LOGGER.info("Telegram listen timeout reached with no usable code; retrying auth.")
    return False


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
                    if not _handle_2fa_required(config, username, sync_state, api=api):
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
