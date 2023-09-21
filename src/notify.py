"""Send an email if the 2FA is expired."""
import datetime
import smtplib

from src import LOGGER, config_parser
from src.email_message import EmailMessage as Message


def send(config, last_send=None, dry_run=False):
    """Send email."""
    sent_on = None
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
        except (Exception) as e:
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
