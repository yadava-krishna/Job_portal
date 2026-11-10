"""backend/services/email_service.py

Transactional and digest email dispatch via SMTP.
Supports SSL/TLS and degrades gracefully when unconfigured.
"""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import logging
import smtplib
from typing import Any

from backend.config import get_settings

log = logging.getLogger(__name__)

# Test hook to intercept outbound mail during unit tests
# Tests set this to a list to capture messages. It stays None in production so nothing (e.g. reset links) is
# ever kept in process memory.
test_outbox: list[dict[str, Any]] | None = None


def is_smtp_configured() -> bool:
    settings = get_settings()
    host = getattr(settings, "smtp_host", None)
    return bool(host and host.strip())


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> bool:
    """Send an email via configured SMTP. Returns True on success, False if skipped/failed."""
    settings = get_settings()
    host = getattr(settings, "smtp_host", None)
    port = getattr(settings, "smtp_port", 465)
    user = getattr(settings, "smtp_user", None)
    password = getattr(settings, "smtp_password", None)
    from_email = getattr(settings, "smtp_from", "JobPilot <no-reply@jobpilot.local>")

    # Check test outbox interceptor
    if test_outbox is not None:
        test_outbox.append({
            "to": to_email,
            "subject": subject,
            "html": html_body,
            "text": text_body,
        })
        if not host:
            return True

    if not host:
        log.debug("SMTP not configured; email to %s dropped (subject: %s)", to_email, subject)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as server:
                if user and password:
                    server.login(user, password)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls()
                if user and password:
                    server.login(user, password)
                server.sendmail(from_email, [to_email], msg.as_string())
        log.info("Email dispatched successfully to %s: %s", to_email, subject)
        return True
    except Exception as exc:
        log.error("Failed to send email to %s: %s", to_email, exc)
        return False
