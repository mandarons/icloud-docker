""" Send an email if the 2FA is expired  """

import smtplib
import datetime
import logging
from mailer import Message
from src import config_parser


def send(config, last_send=None, dry_run=False):
    sent_on = None
    email = config_parser.get_smtp_email(config=config)
    host = config_parser.get_smtp_host(config=config)
    port = config_parser.get_smtp_port(config=config)
    no_tls = config_parser.get_smtp_no_tls(config=config)
    password = config_parser.get_smtp_password(config=config)

    if last_send and last_send > datetime.datetime.now() - datetime.timedelta(hours=24):
        print("Throttling email to once a day")
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
                    smtp.login(email, password)

                msg = build_message(email)

                smtp.sendmail(email, email, msg.as_string())
                smtp.quit()
        except (Exception) as e:
            sent_on = None
            print("Error: failed to send email:" + str(e))
            logging.exception(e)
    else:
        print("Not sending 2FA notification because SMTP is not configured")

    return sent_on


def build_message(email):
    message = Message()
    message.To = email
    message.From = "icloud-drive-docker <" + email + ">"
    message.Date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    message.Subject = "icloud-drive-docker: Two step authentication required"
    message.Body = """Two-step authentication for iCloud Drive (Docker) is required.
Please login to your server and authenticate.  Eg:
`docker exec -it icloud-drive /bin/sh -c "icloud --username=<icloud-username>"`."""

    return message
