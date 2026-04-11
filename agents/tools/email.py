"""Email sending tool for the monitor agent."""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from os import getenv

from agents.tools._helpers import _safe_json


def send_email(
    reason: str,
    to: str = "",
    subject: str = "",
    body: str = "",
) -> str:
    """Send an email report.

    ## When to Use
    Use this tool to deliver monitoring reports or alerts via email.
    The recipient address defaults to the ``MONITOR_EMAIL_TO`` env var.

    ## Parameters
    - ``reason`` (str): Why you are sending this email
    - ``to`` (str): Recipient email address (defaults to ``MONITOR_EMAIL_TO``)
    - ``subject`` (str): Email subject line
    - ``body`` (str): Plain-text email body

    ## Returns
    JSON with:
    - ``result``: ``"sent"`` on success
    - ``error``: Empty on success, or error description
    """
    try:
        smtp_host = getenv("SMTP_HOST", "")
        smtp_port = int(getenv("SMTP_PORT", "587"))
        smtp_user = getenv("SMTP_USER", "")
        smtp_pass = getenv("SMTP_PASS", "")
        smtp_from = getenv("SMTP_FROM", "")
        recipient = to or getenv("MONITOR_EMAIL_TO", "")

        if not smtp_host:
            return _safe_json({"result": "", "error": "SMTP_HOST not configured"})
        if not smtp_user or not smtp_pass:
            return _safe_json(
                {
                    "result": "",
                    "error": "SMTP_USER or SMTP_PASS not configured",
                }
            )
        if not recipient:
            return _safe_json(
                {
                    "result": "",
                    "error": (
                        "No recipient: set 'to' param or " "MONITOR_EMAIL_TO env var"
                    ),
                }
            )
        if not subject:
            return _safe_json({"result": "", "error": "subject is required"})
        if not body:
            return _safe_json({"result": "", "error": "body is required"})

        msg = MIMEMultipart()
        msg["From"] = smtp_from or smtp_user
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from or smtp_user, recipient, msg.as_string())

        return _safe_json({"result": "sent", "error": ""})
    except Exception as exc:
        return _safe_json({"result": "", "error": str(exc)})
