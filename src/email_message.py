"""Email message module."""

import time
import uuid
from email.mime.text import MIMEText
from typing import Any


class EmailMessage:
    """
    Email message class for creating and managing email messages.

    This class handles the creation of email messages with proper formatting
    and MIME structure for sending via SMTP.
    """

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize email message with provided parameters and defaults.

        Args:
            **kwargs: Email parameters including to, from, subject, body, etc.
        """
        params = self._process_email_parameters(kwargs)

        self.to = params.get("to")
        self.rto = params.get("rto")
        self.cc = params.get("cc")
        self.bcc = params.get("bcc")
        self.sender = params.get("from")
        self.subject = params.get("subject", "")
        self.body = params.get("body")
        self.html = params.get("html")
        self.date = params.get("date", self._generate_default_date())
        self.charset = params.get("charset", self._get_default_charset())
        self.headers = params.get("headers", {})

        self.message_id = self.make_key()

    def _process_email_parameters(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """
        Process and normalize email parameters from kwargs.

        This function handles the transformation of keyword arguments into
        a normalized parameter dictionary for email message creation.

        Args:
            kwargs: Raw keyword arguments passed to constructor

        Returns:
            Dict containing processed email parameters
        """
        params = {}
        for item in kwargs.items():
            params[item[0]] = item[1]
        return params

    def _generate_default_date(self) -> str:
        """
        Generate default date string in RFC 2822 format.

        Returns:
            Formatted date string for email headers
        """
        return time.strftime("%a, %d %b %Y %H:%M:%S %z", time.gmtime())

    def _get_default_charset(self) -> str:
        """
        Get default character encoding for email messages.

        Returns:
            Default charset string
        """
        return "us-ascii"

    def make_key(self) -> str:
        """
        Generate unique message ID.

        Creates a unique identifier for the email message using UUID4.

        Returns:
            Unique string identifier for the message
        """
        return str(uuid.uuid4())

    def as_string(self) -> str:
        """
        Return plaintext email content as string.

        This is the main public interface for getting the formatted email
        message ready for sending via SMTP.

        Returns:
            Complete email message as formatted string
        """
        return self._plaintext()

    def _plaintext(self) -> str:
        """
        Create plaintext email content and convert to string.

        Orchestrates the creation of MIME message structure and conversion
        to string format for email transmission.

        Returns:
            Formatted email message string
        """
        msg = self._create_mime_message()
        self._set_info(msg)
        return msg.as_string()

    def _create_mime_message(self) -> MIMEText:
        """
        Create MIME text message object.

        Handles the creation of the core MIME structure with proper
        content and encoding.

        Returns:
            MIMEText object ready for header setting
        """
        # Handle None body by using empty string
        body_text = self.body if self.body is not None else ""
        return MIMEText(body_text, "plain", self.charset)

    def _set_info(self, msg: MIMEText) -> None:
        """
        Set email header information on MIME message.

        Configures the essential email headers (Subject, From, To, Date)
        on the provided MIME message object. Handles None values gracefully.

        Args:
            msg: MIMEText object to configure with headers
        """
        msg["Subject"] = self.subject or ""
        msg["From"] = self.sender or ""
        msg["To"] = self.to or ""
        msg["Date"] = self.date
