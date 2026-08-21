"""Email delivery package.

Public surface:

    from app.email import get_default_email_client, IEmailClient
    from app.email.templates import otp_email

    client = get_default_email_client()
    subject, html, text = otp_email(code="123456", purpose=..., ttl_minutes=10)
    client.send(to=user.email, subject=subject, html=html, text=text)

Provider selection is driven by settings.EMAIL_PROVIDER ("console" |
"resend"); a missing Resend key falls back to console with a warning so a
misconfigured environment degrades to visible-in-logs rather than crashing.
"""

import logging

from app.core.config import settings
from app.email.console_client import ConsoleEmailClient
from app.email.exceptions import EmailAuthError, EmailError, EmailSendError
from app.email.interface import IEmailClient
from app.email.resend_client import ResendEmailClient

logger = logging.getLogger(__name__)

_default_client: IEmailClient | None = None


def get_default_email_client() -> IEmailClient:
    """Build (once) and return the configured email client."""
    global _default_client
    if _default_client is None:
        provider = settings.EMAIL_PROVIDER.lower()
        if provider == "resend" and settings.RESEND_API_KEY:
            _default_client = ResendEmailClient()
        else:
            if provider == "resend":
                logger.warning(
                    "EMAIL_PROVIDER=resend but RESEND_API_KEY is empty — "
                    "falling back to console email client"
                )
            _default_client = ConsoleEmailClient()
    return _default_client


def _reset_default_email_client() -> None:
    """Test hook: drop the singleton so settings changes take effect."""
    global _default_client
    _default_client = None


__all__ = [
    "IEmailClient",
    "ConsoleEmailClient",
    "ResendEmailClient",
    "get_default_email_client",
    "_reset_default_email_client",
    "EmailError",
    "EmailSendError",
    "EmailAuthError",
]
