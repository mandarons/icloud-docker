"""Config file parser.

This module provides high-level configuration retrieval functions.
Low-level utilities are in config_utils.py, logging in config_logging.py,
and filesystem operations in filesystem_utils.py per SRP.
"""

__author__ = "Mandar Patil (mandarons@pm.me)"

import multiprocessing
from typing import Any

from icloudpy.services.photos import PhotoAsset

from src import (
    DEFAULT_DRIVE_DESTINATION,
    DEFAULT_PHOTOS_DESTINATION,
    DEFAULT_RETRY_LOGIN_INTERVAL_SEC,
    DEFAULT_ROOT_DESTINATION,
    DEFAULT_SYNC_INTERVAL_SEC,
    configure_icloudpy_logging,
    get_logger,
)
from src.config_logging import (
    log_config_debug,
    log_config_error,
    log_config_found_info,
    log_config_not_found_warning,
    log_invalid_config_value,
)
from src.config_utils import (
    config_path_to_string,
    get_config_value,
    get_config_value_or_default,
    get_config_value_or_none,
    traverse_config_path,
)
from src.filesystem_utils import ensure_directory_exists, join_and_ensure_path

# Configure icloudpy logging immediately after import
configure_icloudpy_logging()

LOGGER = get_logger()

# Cache for config values to prevent repeated warnings
_config_warning_cache = set()


def _log_config_warning_once(config_path: list, message: str) -> None:
    """Log a configuration warning only once for the given config path.

    Args:
        config_path: Configuration path as list
        message: Warning message to log
    """
    config_path_key = config_path_to_string(config_path)
    if config_path_key not in _config_warning_cache:
        _config_warning_cache.add(config_path_key)
        log_config_not_found_warning(config_path, message)


def clear_config_warning_cache() -> None:
    """Clear the configuration warning cache.

    This function is primarily intended for testing purposes to ensure
    clean test isolation.
    """
    _config_warning_cache.clear()


# =============================================================================
# String Processing Functions
# =============================================================================


def validate_and_strip_username(username: str, config_path: list[str]) -> str | None:
    """Validate and strip username string.

    Args:
        username: Raw username string from config
        config_path: Config path for error logging

    Returns:
        Stripped username if valid, None if empty
    """
    username = username.strip()
    if len(username) == 0:
        log_config_error(config_path, "username is empty")
        return None
    return username


# =============================================================================
# Credential Configuration Functions
# =============================================================================


def get_username(config: dict) -> str | None:
    """Get username from config.

    Args:
        config: Configuration dictionary

    Returns:
        Username string if found and valid, None otherwise
    """
    config_path = ["app", "credentials", "username"]
    if not traverse_config_path(config=config, config_path=config_path):
        log_config_error(config_path, "username is missing. Please set the username.")
        return None

    username = get_config_value(config=config, config_path=config_path)
    return validate_and_strip_username(username, config_path)


def get_retry_login_interval(config: dict) -> int:
    """Return retry login interval from config.

    Args:
        config: Configuration dictionary

    Returns:
        Retry login interval in seconds
    """
    config_path = ["app", "credentials", "retry_login_interval"]

    if not traverse_config_path(config=config, config_path=config_path):
        retry_login_interval = DEFAULT_RETRY_LOGIN_INTERVAL_SEC
        log_config_not_found_warning(
            config_path,
            f"not found. Using default {retry_login_interval} seconds ...",
        )
    else:
        retry_login_interval = get_config_value(config=config, config_path=config_path)
        log_config_found_info(f"Retrying login every {retry_login_interval} seconds.")

    return retry_login_interval


def get_region(config: dict) -> str:
    """Return region from config.

    Args:
        config: Configuration dictionary

    Returns:
        Region string ('global' or 'china')
    """
    config_path = ["app", "region"]
    region = get_config_value_or_default(config=config, config_path=config_path, default="global")

    if region == "global" and not traverse_config_path(config=config, config_path=config_path):
        log_config_not_found_warning(config_path, "not found. Using default value - global ...")
    elif region not in ["global", "china"]:
        log_config_error(
            config_path,
            "is invalid. Valid values are - global or china. Using default value - global ...",
        )
        region = "global"

    return region


# =============================================================================
# Sync Interval Configuration Functions
# =============================================================================


def get_sync_interval(config: dict, config_path: list[str], service_name: str, log_messages: bool = True) -> int:
    """Get sync interval for a service (drive or photos).

    Extracted common logic for retrieving sync intervals.

    Args:
        config: Configuration dictionary
        config_path: Path to sync_interval config
        service_name: Name of service for logging ("drive" or "photos")
        log_messages: Whether to log informational messages (default: True)

    Returns:
        Sync interval in seconds
    """
    sync_interval = get_config_value_or_default(
        config=config,
        config_path=config_path,
        default=DEFAULT_SYNC_INTERVAL_SEC,
    )

    if log_messages:
        if sync_interval == DEFAULT_SYNC_INTERVAL_SEC:
            log_config_not_found_warning(
                config_path,
                f"is not found. Using default sync_interval: {sync_interval} seconds ...",
            )
        else:
            log_config_found_info(f"Syncing {service_name} every {sync_interval} seconds.")

    return sync_interval


def get_drive_sync_interval(config: dict, log_messages: bool = True) -> int:
    """Return drive sync interval from config.

    Args:
        config: Configuration dictionary
        log_messages: Whether to log informational messages (default: True)

    Returns:
        Drive sync interval in seconds
    """
    config_path = ["drive", "sync_interval"]
    return get_sync_interval(config=config, config_path=config_path, service_name="drive", log_messages=log_messages)


def get_photos_sync_interval(config: dict, log_messages: bool = True) -> int:
    """Return photos sync interval from config.

    Args:
        config: Configuration dictionary
        log_messages: Whether to log informational messages (default: True)

    Returns:
        Photos sync interval in seconds
    """
    config_path = ["photos", "sync_interval"]
    return get_sync_interval(config=config, config_path=config_path, service_name="photos", log_messages=log_messages)


# =============================================================================
# Thread Configuration Functions
# =============================================================================


def calculate_default_max_threads() -> int:
    """Calculate default maximum threads based on CPU cores.

    Returns:
        Default max threads (min of CPU count and 8)
    """
    return min(multiprocessing.cpu_count(), 8)


def parse_max_threads_value(max_threads_config: Any, default_max_threads: int) -> int:
    """Parse and validate max_threads configuration value.

    Args:
        max_threads_config: Raw config value (string "auto" or integer)
        default_max_threads: Default value to use

    Returns:
        Validated max threads value (capped at 16)
    """
    # Handle "auto" value
    if isinstance(max_threads_config, str) and max_threads_config.lower() == "auto":
        max_threads = default_max_threads
        log_config_found_info(f"Using automatic thread count: {max_threads} threads (based on CPU cores).")
    elif isinstance(max_threads_config, int) and max_threads_config >= 1:
        max_threads = min(max_threads_config, 16)  # Cap at 16 to avoid overwhelming servers
        log_config_found_info(f"Using configured max_threads: {max_threads}.")
    else:
        log_invalid_config_value(
            ["app", "max_threads"],
            max_threads_config,
            "'auto' or integer >= 1",
        )
        max_threads = default_max_threads

    return max_threads


def get_app_max_threads(config: dict) -> int:
    """Return app-level max threads from config with support for 'auto' value.

    Args:
        config: Configuration dictionary

    Returns:
        Maximum number of threads for parallel operations
    """
    default_max_threads = calculate_default_max_threads()
    config_path = ["app", "max_threads"]

    if not traverse_config_path(config=config, config_path=config_path):
        log_config_debug(
            f"max_threads is not found in {config_path_to_string(config_path=config_path)}. "
            f"Using default max_threads: {default_max_threads} (auto) ...",
        )
        return default_max_threads

    max_threads_config = get_config_value(config=config, config_path=config_path)
    return parse_max_threads_value(max_threads_config, default_max_threads)


def get_usage_tracking_enabled(config: dict) -> bool:
    """Get usage tracking enabled setting from configuration.

    Args:
        config: Configuration dictionary

    Returns:
        True if usage tracking is enabled (default), False if disabled
    """
    config_path = ["app", "usage_tracking", "enabled"]
    if not traverse_config_path(config=config, config_path=config_path):
        return True  # Default to enabled if not configured

    value = get_config_value(config=config, config_path=config_path)
    if isinstance(value, bool):
        return value

    # Handle string values for backwards compatibility
    if isinstance(value, str):
        return value.lower() not in ("false", "no", "0", "disabled", "off")

    # Default to enabled for any other type
    return True


# =============================================================================
# Root Destination Functions
# =============================================================================


def get_root_destination_path(config: dict) -> str:
    """Get root destination path from config without creating directory.

    Args:
        config: Configuration dictionary

    Returns:
        Root destination path string
    """
    config_path = ["app", "root"]
    root_destination = get_config_value_or_default(
        config=config,
        config_path=config_path,
        default=DEFAULT_ROOT_DESTINATION,
    )

    if not traverse_config_path(config=config, config_path=config_path):
        log_config_not_found_warning(
            config_path,
            f"root destination is missing. Using default root destination: {root_destination}",
        )

    return root_destination


def prepare_root_destination(config: dict) -> str:
    """Prepare root destination by creating directory if needed.

    Args:
        config: Configuration dictionary

    Returns:
        Absolute path to root destination directory
    """
    log_config_debug("Checking root destination ...")
    root_destination = get_root_destination_path(config)
    return ensure_directory_exists(root_destination)


# =============================================================================
# Drive Configuration Functions
# =============================================================================


def get_drive_destination_path(config: dict) -> str:
    """Get drive destination path from config without creating directory.

    Args:
        config: Configuration dictionary

    Returns:
        Drive destination path string
    """
    config_path = ["drive", "destination"]
    drive_destination = get_config_value_or_default(
        config=config,
        config_path=config_path,
        default=DEFAULT_DRIVE_DESTINATION,
    )

    if not traverse_config_path(config=config, config_path=config_path):
        log_config_not_found_warning(
            config_path,
            f"destination is missing. Using default drive destination: {drive_destination}.",
        )

    return drive_destination


def prepare_drive_destination(config: dict) -> str:
    """Prepare drive destination path by creating directory if needed.

    Args:
        config: Configuration dictionary

    Returns:
        Absolute path to drive destination directory
    """
    log_config_debug("Checking drive destination ...")
    root_path = prepare_root_destination(config=config)
    drive_destination = get_drive_destination_path(config)
    return join_and_ensure_path(root_path, drive_destination)


def get_drive_remove_obsolete(config: dict) -> bool:
    """Return drive remove obsolete flag from config.

    Args:
        config: Configuration dictionary

    Returns:
        True if obsolete files should be removed, False otherwise
    """
    config_path = ["drive", "remove_obsolete"]
    drive_remove_obsolete = get_config_value_or_default(config=config, config_path=config_path, default=False)

    if not drive_remove_obsolete:
        _log_config_warning_once(
            config_path,
            "remove_obsolete is not found. Not removing the obsolete files and folders.",
        )
    else:
        log_config_debug(f"{'R' if drive_remove_obsolete else 'Not R'}emoving obsolete files and folders ...")

    return drive_remove_obsolete


# =============================================================================
# Photos Configuration Functions
# =============================================================================


def get_photos_destination_path(config: dict) -> str:
    """Get photos destination path from config without creating directory.

    Args:
        config: Configuration dictionary

    Returns:
        Photos destination path string
    """
    config_path = ["photos", "destination"]
    photos_destination = get_config_value_or_default(
        config=config,
        config_path=config_path,
        default=DEFAULT_PHOTOS_DESTINATION,
    )

    if not traverse_config_path(config=config, config_path=config_path):
        log_config_not_found_warning(
            config_path,
            f"destination is missing. Using default photos destination: {config_path_to_string(config_path)}",
        )

    return photos_destination


def prepare_photos_destination(config: dict) -> str:
    """Prepare photos destination path by creating directory if needed.

    Args:
        config: Configuration dictionary

    Returns:
        Absolute path to photos destination directory
    """
    log_config_debug("Checking photos destination ...")
    root_path = prepare_root_destination(config=config)
    photos_destination = get_photos_destination_path(config)
    return join_and_ensure_path(root_path, photos_destination)


def get_photos_all_albums(config: dict) -> bool:
    """Return flag to download all albums from config.

    Args:
        config: Configuration dictionary

    Returns:
        True if all albums should be synced, False otherwise
    """
    config_path = ["photos", "all_albums"]
    download_all = get_config_value_or_default(config=config, config_path=config_path, default=False)

    if download_all:
        log_config_found_info("Syncing all albums.")

    return download_all


def get_photos_use_hardlinks(config: dict, log_messages: bool = True) -> bool:
    """Return flag to use hard links for duplicate photos from config.

    Args:
        config: Configuration dictionary
        log_messages: Whether to log informational messages (default: True)

    Returns:
        True if hard links should be used, False otherwise
    """
    config_path = ["photos", "use_hardlinks"]
    use_hardlinks = get_config_value_or_default(config=config, config_path=config_path, default=False)

    if use_hardlinks and log_messages:
        log_config_found_info("Using hard links for duplicate photos.")

    return use_hardlinks


def get_photos_remove_obsolete(config: dict) -> bool:
    """Return photos remove obsolete flag from config.

    Args:
        config: Configuration dictionary

    Returns:
        True if obsolete files should be removed, False otherwise
    """
    config_path = ["photos", "remove_obsolete"]
    photos_remove_obsolete = get_config_value_or_default(config=config, config_path=config_path, default=False)

    if not photos_remove_obsolete:
        _log_config_warning_once(
            config_path,
            "remove_obsolete is not found. Not removing the obsolete files and folders.",
        )
    else:
        log_config_debug(f"{'R' if photos_remove_obsolete else 'Not R'}emoving obsolete files and folders ...")

    return photos_remove_obsolete


def get_photos_folder_format(config: dict) -> str | None:
    """Return filename format or None.

    Args:
        config: Configuration dictionary

    Returns:
        Folder format string if configured, None otherwise
    """
    config_path = ["photos", "folder_format"]
    fmt = get_config_value_or_none(config=config, config_path=config_path)

    if fmt:
        log_config_found_info(f"Using format {fmt}.")

    return fmt


# =============================================================================
# Photos Filter Configuration Functions
# =============================================================================


def validate_file_sizes(file_sizes: list[str]) -> list[str]:
    """Validate and filter file sizes against valid options.

    Args:
        file_sizes: List of file size strings to validate

    Returns:
        List of valid file sizes (defaults to ["original"] if all invalid)
    """
    valid_file_sizes = list(PhotoAsset.PHOTO_VERSION_LOOKUP.keys())
    validated_sizes = []

    for file_size in file_sizes:
        if file_size not in valid_file_sizes:
            log_invalid_config_value(
                ["photos", "filters", "file_sizes"],
                file_size,
                ",".join(valid_file_sizes),
            )
        else:
            validated_sizes.append(file_size)

    return validated_sizes if validated_sizes else ["original"]


def get_photos_libraries_filter(config: dict, base_config_path: list[str]) -> list[str] | None:
    """Get libraries filter from photos config.

    Args:
        config: Configuration dictionary
        base_config_path: Base path to filters section

    Returns:
        List of library names if configured, None otherwise
    """
    config_path = base_config_path + ["libraries"]
    libraries = get_config_value_or_none(config=config, config_path=config_path)

    if not libraries or len(libraries) == 0:
        log_config_not_found_warning(config_path, "not found. Downloading all libraries ...")
        return None

    return libraries


def get_photos_albums_filter(config: dict, base_config_path: list[str]) -> list[str] | None:
    """Get albums filter from photos config.

    Args:
        config: Configuration dictionary
        base_config_path: Base path to filters section

    Returns:
        List of album names if configured, None otherwise
    """
    config_path = base_config_path + ["albums"]
    albums = get_config_value_or_none(config=config, config_path=config_path)

    if not albums or len(albums) == 0:
        log_config_not_found_warning(config_path, "not found. Downloading all albums ...")
        return None

    return albums


def get_photos_file_sizes_filter(config: dict, base_config_path: list[str]) -> list[str]:
    """Get file sizes filter from photos config.

    Args:
        config: Configuration dictionary
        base_config_path: Base path to filters section

    Returns:
        List of file size options (defaults to ["original"])
    """
    config_path = base_config_path + ["file_sizes"]

    if not traverse_config_path(config=config, config_path=config_path):
        log_config_not_found_warning(config_path, "not found. Downloading original size photos ...")
        return ["original"]

    file_sizes = get_config_value(config=config, config_path=config_path)
    return validate_file_sizes(file_sizes)


def get_photos_extensions_filter(config: dict, base_config_path: list[str]) -> list[str] | None:
    """Get extensions filter from photos config.

    Args:
        config: Configuration dictionary
        base_config_path: Base path to filters section

    Returns:
        List of file extensions if configured, None otherwise
    """
    config_path = base_config_path + ["extensions"]
    extensions = get_config_value_or_none(config=config, config_path=config_path)

    if not extensions or len(extensions) == 0:
        log_config_not_found_warning(config_path, "not found. Downloading all extensions ...")
        return None

    return extensions


def get_photos_filters(config: dict) -> dict[str, Any]:
    """Return photos filters from config.

    Args:
        config: Configuration dictionary

    Returns:
        Dictionary containing filter configuration for photos
    """
    photos_filters = {
        "libraries": None,
        "albums": None,
        "file_sizes": ["original"],
        "extensions": None,
    }

    base_config_path = ["photos", "filters"]

    # Check for filters section existence
    if not traverse_config_path(config=config, config_path=base_config_path):
        log_config_not_found_warning(
            base_config_path,
            "not found. Downloading all libraries and albums with original size ...",
        )
        return photos_filters

    # Parse individual filter components
    photos_filters["libraries"] = get_photos_libraries_filter(config, base_config_path)
    photos_filters["albums"] = get_photos_albums_filter(config, base_config_path)
    photos_filters["file_sizes"] = get_photos_file_sizes_filter(config, base_config_path)
    photos_filters["extensions"] = get_photos_extensions_filter(config, base_config_path)

    return photos_filters


# =============================================================================
# SMTP Configuration Functions
# =============================================================================


def get_smtp_config_value(config: dict, key: str, warn_if_missing: bool = True) -> str | None:
    """Get SMTP configuration value with optional warning.

    Common helper for SMTP config retrieval to reduce duplication.

    Args:
        config: Configuration dictionary
        key: SMTP config key name
        warn_if_missing: Whether to log warning if not found

    Returns:
        Config value if found, None otherwise
    """
    config_path = ["app", "smtp", key]
    value = get_config_value_or_none(config=config, config_path=config_path)

    if value is None and warn_if_missing:
        log_config_not_found_warning(config_path, f"{key} is not found.")

    return value


def get_smtp_email(config: dict) -> str | None:
    """Return smtp from email from config.

    Args:
        config: Configuration dictionary

    Returns:
        SMTP email address if configured, None otherwise
    """
    return get_smtp_config_value(config, "email", warn_if_missing=False)


def get_smtp_username(config: dict) -> str | None:
    """Return smtp username from the config, if set.

    Args:
        config: Configuration dictionary

    Returns:
        SMTP username if configured, None otherwise
    """
    return get_smtp_config_value(config, "username", warn_if_missing=False)


def get_smtp_to_email(config: dict) -> str | None:
    """Return smtp to email from config, defaults to from email.

    Args:
        config: Configuration dictionary

    Returns:
        SMTP 'to' email address, falling back to 'from' email if not specified
    """
    to_email = get_smtp_config_value(config, "to", warn_if_missing=False)
    return to_email if to_email else get_smtp_email(config=config)


def get_smtp_password(config: dict) -> str | None:
    """Return smtp password from config.

    Args:
        config: Configuration dictionary

    Returns:
        SMTP password if configured, None otherwise
    """
    return get_smtp_config_value(config, "password", warn_if_missing=True)


def get_smtp_host(config: dict) -> str | None:
    """Return smtp host from config.

    Args:
        config: Configuration dictionary

    Returns:
        SMTP host if configured, None otherwise
    """
    return get_smtp_config_value(config, "host", warn_if_missing=True)


def get_smtp_port(config: dict) -> int | None:
    """Return smtp port from config.

    Args:
        config: Configuration dictionary

    Returns:
        SMTP port if configured, None otherwise
    """
    return get_smtp_config_value(config, "port", warn_if_missing=True)  # type: ignore[return-value]


def get_smtp_no_tls(config: dict) -> bool:
    """Return smtp no_tls flag from config.

    Args:
        config: Configuration dictionary

    Returns:
        True if TLS should be disabled, False otherwise
    """
    no_tls = get_smtp_config_value(config, "no_tls", warn_if_missing=True)
    return no_tls if no_tls is not None else False  # type: ignore[return-value]


# =============================================================================
# Notification Service Configuration Functions
# =============================================================================


def get_notification_config_value(config: dict, service: str, key: str) -> str | None:
    """Get notification service configuration value.

    Common helper for notification service config retrieval.

    Args:
        config: Configuration dictionary
        service: Service name (telegram, discord, pushover)
        key: Config key name

    Returns:
        Config value if found, None otherwise
    """
    config_path = ["app", service, key]
    value = get_config_value_or_none(config=config, config_path=config_path)

    if value is None:
        log_config_not_found_warning(config_path, f"{key} is not found.")

    return value


def get_telegram_bot_token(config: dict) -> str | None:
    """Return telegram bot token from config.

    Args:
        config: Configuration dictionary

    Returns:
        Telegram bot token if configured, None otherwise
    """
    return get_notification_config_value(config, "telegram", "bot_token")


def get_telegram_chat_id(config: dict) -> str | None:
    """Return telegram chat id from config.

    Args:
        config: Configuration dictionary

    Returns:
        Telegram chat ID if configured, None otherwise
    """
    return get_notification_config_value(config, "telegram", "chat_id")


def get_discord_webhook_url(config: dict) -> str | None:
    """Return discord webhook_url from config.

    Args:
        config: Configuration dictionary

    Returns:
        Discord webhook URL if configured, None otherwise
    """
    return get_notification_config_value(config, "discord", "webhook_url")


def get_discord_username(config: dict) -> str | None:
    """Return discord username from config.

    Args:
        config: Configuration dictionary

    Returns:
        Discord username if configured, None otherwise
    """
    return get_notification_config_value(config, "discord", "username")


def get_pushover_user_key(config: dict) -> str | None:
    """Return Pushover user key from config.

    Args:
        config: Configuration dictionary

    Returns:
        Pushover user key if configured, None otherwise
    """
    return get_notification_config_value(config, "pushover", "user_key")


def get_pushover_api_token(config: dict) -> str | None:
    """Return Pushover API token from config.

    Args:
        config: Configuration dictionary

    Returns:
        Pushover API token if configured, None otherwise
    """
    return get_notification_config_value(config, "pushover", "api_token")


# =============================================================================
# Sync Summary Notification Configuration Functions
# =============================================================================


def get_sync_summary_enabled(config: dict) -> bool:
    """Return whether sync summary notifications are enabled.

    Args:
        config: Configuration dictionary

    Returns:
        True if sync summary is enabled, False otherwise (default: False)
    """
    config_path = ["app", "notifications", "sync_summary", "enabled"]
    if not traverse_config_path(config=config, config_path=config_path):
        return False

    value = get_config_value(config=config, config_path=config_path)
    return bool(value) if value is not None else False


def get_sync_summary_on_success(config: dict) -> bool:
    """Return whether to send summary on successful syncs.

    Args:
        config: Configuration dictionary

    Returns:
        True if should send on success, False otherwise (default: True)
    """
    config_path = ["app", "notifications", "sync_summary", "on_success"]
    if not traverse_config_path(config=config, config_path=config_path):
        return True  # Default to True if not configured

    value = get_config_value(config=config, config_path=config_path)
    return bool(value) if value is not None else True


def get_sync_summary_on_error(config: dict) -> bool:
    """Return whether to send summary when errors occur.

    Args:
        config: Configuration dictionary

    Returns:
        True if should send on error, False otherwise (default: True)
    """
    config_path = ["app", "notifications", "sync_summary", "on_error"]
    if not traverse_config_path(config=config, config_path=config_path):
        return True  # Default to True if not configured

    value = get_config_value(config=config, config_path=config_path)
    return bool(value) if value is not None else True


def get_sync_summary_min_downloads(config: dict) -> int:
    """Return minimum downloads required to trigger notification.

    Args:
        config: Configuration dictionary

    Returns:
        Minimum downloads threshold (default: 1)
    """
    config_path = ["app", "notifications", "sync_summary", "min_downloads"]
    if not traverse_config_path(config=config, config_path=config_path):
        return 1  # Default to 1 if not configured

    value = get_config_value(config=config, config_path=config_path)
    return int(value) if value is not None else 1
