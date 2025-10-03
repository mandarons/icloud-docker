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
    msg = Message(to=to_email)
    msg.sender = "icloud-docker <" + email + ">"
    msg.date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    msg.subject = subject
    msg.body = message
    return msg
