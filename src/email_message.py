import uuid
import time

from email.mime.text import MIMEText


class EmailMessage(object):
    def __init__(self, **kwargs):

        params = {}
        for item in kwargs.items():
            params[item[0]] = item[1]

        self.to = params.get("to", None)
        self.rto = params.get("rto", None)
        self.cc = params.get("cc", None)
        self.bcc = params.get("bcc", None)
        self.sender = params.get("from", None)
        self.subject = params.get("subject", "")
        self.body = params.get("body", None)
        self.html = params.get("html", None)
        self.date = params.get(
            "date", time.strftime("%a, %d %b %Y %H:%M:%S %z", time.gmtime())
        )
        self.charset = params.get("charset", "us-ascii")
        self.headers = params.get("headers", {})

        self.message_id = self.make_key()

    def make_key(self):
        return str(uuid.uuid4())

    def as_string(self):
        return self._plaintext()

    def _plaintext(self):
        msg = MIMEText(self.body, "plain", self.charset)
        self._set_info(msg)
        return msg.as_string()

    def _set_info(self, msg):
        msg["Subject"] = self.subject
        msg["From"] = self.sender
        msg["To"] = self.to
        msg["Date"] = self.date
