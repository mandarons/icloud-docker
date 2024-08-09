"""Email message module."""

import time
import uuid
from email.mime.text import MIMEText


class EmailMessage:
    """Email message class."""

    def __init__(self, **kwargs):
        """Init with defaults."""
        params = {}
        for item in kwargs.items():
            params[item[0]] = item[1]

        self.to = params.get("to")
        self.rto = params.get("rto")
        self.cc = params.get("cc")
        self.bcc = params.get("bcc")
        self.sender = params.get("from")
        self.subject = params.get("subject", "")
        self.body = params.get("body")
        self.html = params.get("html")
        self.date = params.get("date", time.strftime("%a, %d %b %Y %H:%M:%S %z", time.gmtime()))
        self.charset = params.get("charset", "us-ascii")
        self.headers = params.get("headers", {})

        self.message_id = self.make_key()

    def make_key(self):
        """Generate unique key."""
        return str(uuid.uuid4())

    def as_string(self):
        """Return plaintext content."""
        return self._plaintext()

    def _plaintext(self):
        """Create plaintext content."""
        msg = MIMEText(self.body, "plain", self.charset)
        self._set_info(msg)
        return msg.as_string()

    def _set_info(self, msg):
        """Set email information."""
        msg["Subject"] = self.subject
        msg["From"] = self.sender
        msg["To"] = self.to
        msg["Date"] = self.date
