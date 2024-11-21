"""Send an email if the 2FA is expired."""

import datetime
import smtplib

import requests

from src import config_parser, get_logger
from src.email_message import EmailMessage as Message

LOGGER = get_logger()


def notify_telegram(config, message, last_send=None, dry_run=False):
    """Send telegram notification."""
    sent_on = None
    bot_token = config_parser.get_telegram_bot_token(config=config)
    chat_id = config_parser.get_telegram_chat_id(config=config)

    if last_send and last_send > datetime.datetime.now() - datetime.timedelta(hours=24):
        LOGGER.info("Throttling telegram to once a day")
        sent_on = last_send
    elif bot_token and chat_id:
        sent_on = datetime.datetime.now()
        if not dry_run:
            # Post message to telegram bot using API
            if not post_message_to_telegram(
                bot_token,
                chat_id,
                message,
            ):
                sent_on = None
    else:
        LOGGER.warning("Not sending 2FA notification because Telegram is not configured.")
    return sent_on


def post_message_to_telegram(bot_token, chat_id, message):
    """Post message to telegram bot using API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    params = {"chat_id": chat_id, "text": message}
    response = requests.post(url, params=params, timeout=10)
    if response.status_code == 200:
        return True
    # Log error message
    LOGGER.error(f"Failed to send telegram notification. Response: {response.text}")
    return False


def post_message_to_discord(webhook_url, username, message):
    """Post message to discord webhook."""
    data = {"username": username, "content": message}
    response = requests.post(webhook_url, data=data, timeout=10)
    if response.status_code == 204:
        return True
    # Log error message
    LOGGER.error(f"Failed to send Discord notification. Response: {response.text}")
    return False


def notify_discord(config, message, last_send=None, dry_run=False):
    """Send discord notification."""
    sent_on = None
    webhook_url = config_parser.get_discord_webhook_url(config=config)
    username = config_parser.get_discord_username(config=config)

    if last_send and last_send > datetime.datetime.now() - datetime.timedelta(hours=24):
        LOGGER.info("Throttling discord to once a day")
        sent_on = last_send
    elif webhook_url and username:
        sent_on = datetime.datetime.now()
        if not dry_run:
            # Post message to discord webhook using API
            if not post_message_to_discord(webhook_url, username, message):
                sent_on = None
    else:
        LOGGER.warning("Not sending 2FA notification because Discord is not configured.")
    return sent_on


def send(config, username, last_send=None, dry_run=False, region="global"):
    """Send notifications."""
    sent_on = None
    region_opt = ""
    if region != "global":
        region_opt = f"--region={region} "
    message = f"""Two-step authentication for iCloud Drive, Photos (Docker) is required.
                Please login to your server and authenticate. Please run -
                `docker exec -it --user=abc icloud /bin/sh -c
                "icloud --session-directory=/config/session_data {region_opt}--username={username}"`."""
    subject = f"icloud-docker: Two step authentication is required for {username}"
    notify_telegram(config=config, message=message, last_send=last_send, dry_run=dry_run)
    notify_discord(config=config, message=message, last_send=last_send, dry_run=dry_run)
    email = config_parser.get_smtp_email(config=config)
    to_email = config_parser.get_smtp_to_email(config=config)
    host = config_parser.get_smtp_host(config=config)
    port = config_parser.get_smtp_port(config=config)
    no_tls = config_parser.get_smtp_no_tls(config=config)
    username = config_parser.get_smtp_username(config=config)
    password = config_parser.get_smtp_password(config=config)

    if last_send and last_send > datetime.datetime.now() - datetime.timedelta(hours=24):
        LOGGER.info("Throttling email to once a day")
        sent_on = last_send
    elif email and host and port:
        try:
            sent_on = datetime.datetime.now()
            if not dry_run:
                smtp = smtplib.SMTP(host, port)
                smtp.set_debuglevel(0)
                smtp.connect(host, port)
                if not no_tls:
                    smtp.starttls()

                if password:
                    if username:
                        smtp.login(username, password)
                    else:
                        smtp.login(email, password)

                msg = build_message(email, to_email, message, subject)

                smtp.sendmail(from_addr=email, to_addrs=to_email, msg=msg.as_string())
                smtp.quit()
        except Exception as e:
            sent_on = None
            LOGGER.error(f"Failed to send email: {e!s}.")
    else:
        LOGGER.warning("Not sending 2FA notification because SMTP is not configured")

    return sent_on


def build_message(email, to_email, message, subject):
    """Create email message."""
    msg = Message(to=to_email)
    msg.sender = "icloud-docker <" + email + ">"
    msg.date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    msg.subject = subject
    msg.body = message

    return msg
