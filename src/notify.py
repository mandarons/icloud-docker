"""Send an email if the 2FA is expired."""
import datetime
import smtplib

import requests

from src import LOGGER, config_parser
from src.email_message import EmailMessage as Message


def notify_telegram(config, last_send=None, dry_run=False):
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
                """Two-step authentication for iCloud Drive, Photos (Docker) is required.
                Please login to your server and authenticate. Please run -
                `docker exec -it icloud /bin/sh -c "icloud --username=<icloud-username>
                --session-directory=/app/session_data"`.""",
            ):
                sent_on = None
    else:
        LOGGER.warning(
            "Not sending 2FA notification because Telegram is not configured."
        )
    return sent_on


def post_message_to_telegram(bot_token, chat_id, message):
    """Post message to telegram bot using API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    params = {"chat_id": chat_id, "text": message}
    response = requests.post(url, params=params, timeout=10)
    if response.status_code == 200:
        return True
    else:
        # Log error message
        LOGGER.error(f"Failed to send telegram notification. Response: {response.text}")
        return False


def send(config, last_send=None, dry_run=False):
    """Send notifications."""
    sent_on = None
    notify_telegram(config=config, last_send=last_send, dry_run=dry_run)
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

                msg = build_message(email, to_email)

                smtp.sendmail(from_addr=email, to_addrs=to_email, msg=msg.as_string())
                smtp.quit()
        except Exception as e:
            sent_on = None
            LOGGER.error(f"Failed to send email: {str(e)}.")
    else:
        LOGGER.warning("Not sending 2FA notification because SMTP is not configured")

    return sent_on


def build_message(email, to_email):
    """Create email message."""
    message = Message(to=to_email)
    message.sender = "icloud-docker <" + email + ">"
    message.date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    message.subject = "icloud-docker: Two step authentication required"
    message.body = """Two-step authentication for iCloud Drive, Photos (Docker) is required.
Please login to your server and authenticate. Please run -
`docker exec -it icloud /bin/sh -c "icloud --username=<icloud-username> --session-directory=/app/session_data"`."""

    return message
