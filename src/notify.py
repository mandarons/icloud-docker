"""Send notifications when 2FA is required for iCloud authentication."""

import datetime
import smtplib
from typing import Optional

import requests

from src import config_parser, get_logger
from src.email_message import EmailMessage as Message

LOGGER = get_logger()

# Throttling period for notifications (24 hours)
THROTTLE_HOURS = 24


def _is_throttled(last_send) -> bool:
    """
    Check if notification should be throttled based on last send time.

    Args:
        last_send: The datetime when notification was last sent, or None

    Returns:
        True if notification should be throttled, False otherwise
    """
    if last_send is None:
        return False
    if not isinstance(last_send, datetime.datetime):
        return False
    return last_send > datetime.datetime.now() - datetime.timedelta(hours=THROTTLE_HOURS)


def _create_2fa_message(username: str, region: str = "global") -> tuple[str, str]:
    """
    Create the 2FA notification message and subject.

    Args:
        username: The iCloud username requiring 2FA
        region: The iCloud region (default: "global")

    Returns:
        Tuple of (message, subject)
    """
    region_opt = "" if region == "global" else f"--region={region} "
    message = f"""Two-step authentication for iCloud Drive, Photos (Docker) is required.
                Please login to your server and authenticate. Please run -
                `docker exec -it icloud /bin/sh -c "su-exec abc icloud --session-directory=/config/session_data {region_opt}--username={username}"`."""  # noqa: E501
    subject = f"icloud-docker: Two step authentication is required for {username}"
    return message, subject


def _get_current_timestamp() -> datetime.datetime:
    """
    Get the current timestamp for notification tracking.

    Returns:
        Current datetime
    """
    return datetime.datetime.now()


def _get_telegram_config(config) -> tuple[Optional[str], Optional[str], bool]:
    """
    Extract Telegram configuration from config.

    Args:
        config: The configuration dictionary

    Returns:
        Tuple of (bot_token, chat_id, is_configured)
    """
    bot_token = config_parser.get_telegram_bot_token(config=config)
    chat_id = config_parser.get_telegram_chat_id(config=config)
    is_configured = bool(bot_token and chat_id)
    return bot_token, chat_id, is_configured


def notify_telegram(config, message, last_send=None, dry_run=False):
    """
    Send Telegram notification with throttling and error handling.

    Args:
        config: Configuration dictionary
        message: Message to send
        last_send: Timestamp of last send for throttling
        dry_run: If True, don't actually send the message

    Returns:
        Timestamp when message was sent, or last_send if throttled, or None if failed
    """
    if _is_throttled(last_send):
        LOGGER.info("Throttling telegram to once a day")
        return last_send

    bot_token, chat_id, is_configured = _get_telegram_config(config)
    if not is_configured:
        LOGGER.warning("Not sending 2FA notification because Telegram is not configured.")
        return None

    sent_on = _get_current_timestamp()
    if dry_run:
        return sent_on

    # bot_token and chat_id are guaranteed to be non-None due to is_configured check
    if post_message_to_telegram(bot_token, chat_id, message):  # type: ignore[arg-type]
        return sent_on
    return None


def post_message_to_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    """
    Post message to Telegram bot using API.

    Args:
        bot_token: Telegram bot token
        chat_id: Telegram chat ID
        message: Message to send

    Returns:
        True if message was sent successfully, False otherwise
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    params = {"chat_id": chat_id, "text": message}
    response = requests.post(url, params=params, timeout=10)
    if response.status_code == 200:
        return True
    # Log error message
    LOGGER.error(f"Failed to send telegram notification. Response: {response.text}")
    return False


def _get_discord_config(config) -> tuple[Optional[str], Optional[str], bool]:
    """
    Extract Discord configuration from config.

    Args:
        config: The configuration dictionary

    Returns:
        Tuple of (webhook_url, username, is_configured)
    """
    webhook_url = config_parser.get_discord_webhook_url(config=config)
    username = config_parser.get_discord_username(config=config)
    is_configured = bool(webhook_url and username)
    return webhook_url, username, is_configured


def post_message_to_discord(webhook_url: str, username: str, message: str) -> bool:
    """
    Post message to Discord webhook.

    Args:
        webhook_url: Discord webhook URL
        username: Username to display in Discord
        message: Message to send

    Returns:
        True if message was sent successfully, False otherwise
    """
    data = {"username": username, "content": message}
    response = requests.post(webhook_url, data=data, timeout=10)
    if response.status_code == 204:
        return True
    # Log error message
    LOGGER.error(f"Failed to send Discord notification. Response: {response.text}")
    return False


def notify_discord(config, message, last_send=None, dry_run=False):
    """
    Send Discord notification with throttling and error handling.

    Args:
        config: Configuration dictionary
        message: Message to send
        last_send: Timestamp of last send for throttling
        dry_run: If True, don't actually send the message

    Returns:
        Timestamp when message was sent, or last_send if throttled, or None if failed
    """
    if _is_throttled(last_send):
        LOGGER.info("Throttling discord to once a day")
        return last_send

    webhook_url, username, is_configured = _get_discord_config(config)
    if not is_configured:
        LOGGER.warning("Not sending 2FA notification because Discord is not configured.")
        return None

    sent_on = _get_current_timestamp()
    if dry_run or post_message_to_discord(webhook_url, username, message):  # type: ignore[arg-type]
        return sent_on
    return None


def _get_pushover_config(config) -> tuple[Optional[str], Optional[str], bool]:
    """
    Extract Pushover configuration from config.

    Args:
        config: The configuration dictionary

    Returns:
        Tuple of (user_key, api_token, is_configured)
    """
    user_key = config_parser.get_pushover_user_key(config=config)
    api_token = config_parser.get_pushover_api_token(config=config)
    is_configured = bool(user_key and api_token)
    return user_key, api_token, is_configured


def post_message_to_pushover(api_token: str, user_key: str, message: str) -> bool:
    """
    Post message to Pushover API.

    Args:
        api_token: Pushover API token
        user_key: Pushover user key
        message: Message to send

    Returns:
        True if message was sent successfully, False otherwise
    """
    url = "https://api.pushover.net/1/messages.json"
    data = {"token": api_token, "user": user_key, "message": message}
    response = requests.post(url, data=data, timeout=10)
    if response.status_code == 200:
        return True
    LOGGER.error(f"Failed to send Pushover notification. Response: {response.text}")
    return False


def notify_pushover(config, message, last_send=None, dry_run=False):
    """
    Send Pushover notification with throttling and error handling.

    Args:
        config: Configuration dictionary
        message: Message to send
        last_send: Timestamp of last send for throttling
        dry_run: If True, don't actually send the message

    Returns:
        Timestamp when message was sent, or last_send if throttled, or None if failed
    """
    if _is_throttled(last_send):
        LOGGER.info("Throttling Pushover to once a day")
        return last_send

    user_key, api_token, is_configured = _get_pushover_config(config)
    if not is_configured:
        LOGGER.warning("Not sending 2FA notification because Pushover is not configured.")
        return None

    sent_on = _get_current_timestamp()
    if dry_run:
        return sent_on

    # user_key and api_token are guaranteed to be non-None due to is_configured check
    if post_message_to_pushover(api_token, user_key, message):  # type: ignore[arg-type]
        return sent_on
    return None


def notify_email(config, message: str, subject: str, last_send=None, dry_run=False):
    """
    Send email notification with throttling and error handling.

    Args:
        config: Configuration dictionary
        message: Message to send
        subject: Email subject
        last_send: Timestamp of last send for throttling
        dry_run: If True, don't actually send the message

    Returns:
        Timestamp when message was sent, or last_send if throttled, or None if failed
    """
    if _is_throttled(last_send):
        LOGGER.info("Throttling email to once a day")
        return last_send

    email, to_email, host, port, no_tls, username, password, is_configured = _get_smtp_config(config)
    if not is_configured:
        LOGGER.warning("Not sending 2FA notification because SMTP is not configured")
        return None

    sent_on = _get_current_timestamp()
    if dry_run:
        return sent_on

    try:
        # All necessary config values are guaranteed to be non-None due to is_configured check
        smtp = _create_smtp_connection(host, port, no_tls)  # type: ignore[arg-type]

        if password:
            _authenticate_smtp(smtp, email, username, password)  # type: ignore[arg-type]

        # to_email could be None, use email as fallback
        recipient = to_email if to_email else email
        msg = build_message(email, recipient, message, subject)  # type: ignore[arg-type]
        _send_email_message(smtp, email, recipient, msg)  # type: ignore[arg-type]
        smtp.quit()
        return sent_on
    except Exception as e:
        LOGGER.error(f"Failed to send email: {e!s}.")
        return None


def send(config, username, last_send=None, dry_run=False, region="global"):
    """
    Send 2FA notification to all configured notification services.

    Args:
        config: Configuration dictionary
        username: iCloud username requiring 2FA
        last_send: Timestamp of last send for throttling
        dry_run: If True, don't actually send notifications
        region: iCloud region (default: "global")

    Returns:
        Timestamp when notifications were sent, or None if all failed
    """
    message, subject = _create_2fa_message(username, region)

    # Send to all notification services
    telegram_sent = notify_telegram(config=config, message=message, last_send=last_send, dry_run=dry_run)
    discord_sent = notify_discord(config=config, message=message, last_send=last_send, dry_run=dry_run)
    pushover_sent = notify_pushover(config=config, message=message, last_send=last_send, dry_run=dry_run)
    email_sent = notify_email(config=config, message=message, subject=subject, last_send=last_send, dry_run=dry_run)

    # Return the timestamp if any notification was sent successfully
    sent_timestamps = [t for t in [telegram_sent, discord_sent, pushover_sent, email_sent] if t is not None]
    return sent_timestamps[0] if sent_timestamps else None


def _get_smtp_config(
    config,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[int], bool, Optional[str], Optional[str], bool]:
    """
    Extract SMTP configuration from config.

    Args:
        config: The configuration dictionary

    Returns:
        Tuple of (email, to_email, host, port, no_tls, username, password, is_configured)
    """
    email = config_parser.get_smtp_email(config=config)
    to_email = config_parser.get_smtp_to_email(config=config)
    host = config_parser.get_smtp_host(config=config)
    port = config_parser.get_smtp_port(config=config)
    no_tls = config_parser.get_smtp_no_tls(config=config)
    username = config_parser.get_smtp_username(config=config)
    password = config_parser.get_smtp_password(config=config)
    is_configured = bool(email and host and port)
    return email, to_email, host, port, no_tls, username, password, is_configured


def _create_smtp_connection(host: str, port: int, no_tls: bool) -> smtplib.SMTP:
    """
    Create and configure SMTP connection.

    Args:
        host: SMTP host
        port: SMTP port
        no_tls: Whether to skip TLS

    Returns:
        Configured SMTP connection
    """
    smtp = smtplib.SMTP(host, port)
    smtp.set_debuglevel(0)
    smtp.connect(host, port)
    if not no_tls:
        smtp.starttls()
    return smtp


def _authenticate_smtp(smtp: smtplib.SMTP, email: str, username: Optional[str], password: str) -> None:
    """
    Authenticate SMTP connection.

    Args:
        smtp: SMTP connection
        email: Email address for fallback authentication
        username: SMTP username (optional)
        password: SMTP password
    """
    if username:
        smtp.login(username, password)
    else:
        smtp.login(email, password)


def _send_email_message(smtp: smtplib.SMTP, email: str, to_email: str, message_obj: Message) -> None:
    """
    Send email message through SMTP connection.

    Args:
        smtp: SMTP connection
        email: From email address
        to_email: To email address
        message_obj: Email message object
    """
    smtp.sendmail(from_addr=email, to_addrs=to_email, msg=message_obj.as_string())


def _contains_non_ascii(text: Optional[str]) -> bool:
    """Determine if the provided text contains non-ASCII characters."""

    if text is None:
        return False

    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        return True
    return False


def build_message(email: str, to_email: str, message: str, subject: str) -> Message:
    """
    Create email message with proper headers.

    Args:
        email: From email address
        to_email: To email address
        message: Message body
        subject: Message subject

    Returns:
        Configured email message object
    """
    requires_utf8 = _contains_non_ascii(message) or _contains_non_ascii(subject)
    charset = "utf-8" if requires_utf8 else "us-ascii"

    msg = Message(to=to_email, charset=charset)
    msg.sender = "icloud-docker <" + email + ">"
    msg.date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    msg.subject = subject
    msg.body = message
    return msg


# =============================================================================
# Sync Summary Notification Functions
# =============================================================================


def _format_sync_summary_message(summary) -> tuple[str, str]:
    """
    Format sync summary as notification message.

    Args:
        summary: SyncSummary object containing sync statistics

    Returns:
        Tuple of (message, subject)
    """
    from src.sync_stats import format_bytes, format_duration

    has_errors = summary.has_errors()
    status_emoji = "⚠️" if has_errors else "✅"
    status_text = "Completed with Errors" if has_errors else "Complete"

    message_lines = [f"{status_emoji} iCloud Sync {status_text}", ""]

    # Drive statistics
    if summary.drive_stats and summary.drive_stats.has_activity():
        drive = summary.drive_stats
        message_lines.append("📁 Drive:")
        if drive.files_downloaded > 0:
            size_str = format_bytes(drive.bytes_downloaded)
            message_lines.append(f"  • Downloaded: {drive.files_downloaded} files ({size_str})")
        if drive.files_skipped > 0:
            message_lines.append(f"  • Skipped: {drive.files_skipped} files (up-to-date)")
        if drive.files_removed > 0:
            message_lines.append(f"  • Removed: {drive.files_removed} obsolete files")
        if drive.duration_seconds > 0:
            duration_str = format_duration(drive.duration_seconds)
            message_lines.append(f"  • Duration: {duration_str}")
        if drive.has_errors():
            message_lines.append(f"  • Errors: {len(drive.errors)} failed")
        message_lines.append("")

    # Photos statistics
    if summary.photo_stats and summary.photo_stats.has_activity():
        photos = summary.photo_stats
        message_lines.append("📷 Photos:")
        if photos.photos_downloaded > 0:
            size_str = format_bytes(photos.bytes_downloaded)
            message_lines.append(f"  • Downloaded: {photos.photos_downloaded} photos ({size_str})")
        if photos.photos_hardlinked > 0:
            message_lines.append(f"  • Hard-linked: {photos.photos_hardlinked} photos")
        if photos.bytes_saved_by_hardlinks > 0:
            saved_str = format_bytes(photos.bytes_saved_by_hardlinks)
            message_lines.append(f"  • Storage saved: {saved_str}")
        if photos.albums_synced:
            albums_str = ", ".join(photos.albums_synced[:5])
            if len(photos.albums_synced) > 5:
                albums_str += f" (+{len(photos.albums_synced) - 5} more)"
            message_lines.append(f"  • Albums: {albums_str}")
        if photos.duration_seconds > 0:
            duration_str = format_duration(photos.duration_seconds)
            message_lines.append(f"  • Duration: {duration_str}")
        if photos.has_errors():
            message_lines.append(f"  • Errors: {len(photos.errors)} failed")
        message_lines.append("")

    # Error details if present
    if has_errors:
        message_lines.append("Failed items:")
        all_errors = []
        if summary.drive_stats:
            all_errors.extend(summary.drive_stats.errors[:5])  # Limit to first 5
        if summary.photo_stats:
            all_errors.extend(summary.photo_stats.errors[:5])  # Limit to first 5
        message_lines.extend([f"  • {error}" for error in all_errors[:10]])
        total_errors = 0
        if summary.drive_stats:
            total_errors += len(summary.drive_stats.errors)
        if summary.photo_stats:
            total_errors += len(summary.photo_stats.errors)
        if total_errors > 10:
            message_lines.append(f"  ... and {total_errors - 10} more errors")
        message_lines.append("")

    message = "\n".join(message_lines)
    subject = f"icloud-docker: Sync {status_text}"
    return message, subject


def _should_send_sync_summary(config, summary) -> bool:
    """
    Determine if sync summary notification should be sent.

    Args:
        config: Configuration dictionary
        summary: SyncSummary object

    Returns:
        True if notification should be sent, False otherwise
    """
    # Check if sync summary is enabled
    if not config_parser.get_sync_summary_enabled(config=config):
        return False

    # Check if there was any activity
    if not summary.has_activity():
        return False

    # Check error/success preferences
    has_errors = summary.has_errors()
    on_error = config_parser.get_sync_summary_on_error(config=config)
    on_success = config_parser.get_sync_summary_on_success(config=config)

    if has_errors and not on_error:
        return False
    if not has_errors and not on_success:
        return False

    # Check minimum downloads threshold
    min_downloads = config_parser.get_sync_summary_min_downloads(config=config)
    total_downloads = 0
    if summary.drive_stats:
        total_downloads += summary.drive_stats.files_downloaded
    if summary.photo_stats:
        total_downloads += summary.photo_stats.photos_downloaded

    if total_downloads < min_downloads:
        return False

    return True


def send_sync_summary(config, summary, dry_run=False):
    """
    Send sync summary notification to all configured services.

    Note: Sync summaries are NOT throttled like 2FA notifications,
    as they provide valuable operational information for each sync.

    Args:
        config: Configuration dictionary
        summary: SyncSummary object containing sync statistics
        dry_run: If True, don't actually send notifications

    Returns:
        True if at least one notification was sent successfully, False otherwise
    """
    if not _should_send_sync_summary(config, summary):
        LOGGER.debug("Sync summary notification skipped (not enabled or no activity)")
        return False

    message, subject = _format_sync_summary_message(summary)

    # Send to all notification services (no throttling for sync summaries)
    telegram_sent = _send_telegram_no_throttle(config, message, dry_run)
    discord_sent = _send_discord_no_throttle(config, message, dry_run)
    pushover_sent = _send_pushover_no_throttle(config, message, dry_run)
    email_sent = _send_email_no_throttle(config, message, subject, dry_run)

    # Return True if any notification was sent successfully
    any_sent = any([telegram_sent, discord_sent, pushover_sent, email_sent])
    if any_sent:
        LOGGER.info("Sync summary notification sent successfully")
    return any_sent


def _send_telegram_no_throttle(config, message: str, dry_run: bool) -> bool:
    """Send Telegram notification without throttling.

    Args:
        config: Configuration dictionary
        message: Message to send
        dry_run: If True, don't actually send

    Returns:
        True if sent successfully, False otherwise
    """
    bot_token, chat_id, is_configured = _get_telegram_config(config)
    if not is_configured:
        return False

    if dry_run:
        return True

    return post_message_to_telegram(bot_token, chat_id, message)  # type: ignore[arg-type]


def _send_discord_no_throttle(config, message: str, dry_run: bool) -> bool:
    """Send Discord notification without throttling.

    Args:
        config: Configuration dictionary
        message: Message to send
        dry_run: If True, don't actually send

    Returns:
        True if sent successfully, False otherwise
    """
    webhook_url, username, is_configured = _get_discord_config(config)
    if not is_configured:
        return False

    if dry_run:
        return True

    return post_message_to_discord(webhook_url, username, message)  # type: ignore[arg-type]


def _send_pushover_no_throttle(config, message: str, dry_run: bool) -> bool:
    """Send Pushover notification without throttling.

    Args:
        config: Configuration dictionary
        message: Message to send
        dry_run: If True, don't actually send

    Returns:
        True if sent successfully, False otherwise
    """
    user_key, api_token, is_configured = _get_pushover_config(config)
    if not is_configured:
        return False

    if dry_run:
        return True

    return post_message_to_pushover(api_token, user_key, message)  # type: ignore[arg-type]


def _send_email_no_throttle(config, message: str, subject: str, dry_run: bool) -> bool:
    """Send email notification without throttling.

    Args:
        config: Configuration dictionary
        message: Message to send
        subject: Email subject
        dry_run: If True, don't actually send

    Returns:
        True if sent successfully, False otherwise
    """
    email, to_email, host, port, no_tls, username, password, is_configured = _get_smtp_config(config)
    if not is_configured:
        return False

    if dry_run:
        return True

    try:
        smtp = _create_smtp_connection(host, port, no_tls)  # type: ignore[arg-type]

        if password:
            _authenticate_smtp(smtp, email, username, password)  # type: ignore[arg-type]

        recipient = to_email if to_email else email
        msg = build_message(email, recipient, message, subject)  # type: ignore[arg-type]
        _send_email_message(smtp, email, recipient, msg)  # type: ignore[arg-type]
        smtp.quit()
        return True
    except Exception as e:
        LOGGER.error(f"Failed to send sync summary email: {e!s}")
        return False
