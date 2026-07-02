"""Email delivery via SMTP (Sprint 9).

Mirrors the other external gateways (OtpGateway/InviteGateway/FcmGateway): the real
send lives here so tests swap a fake via a FastAPI dependency override, and it **never
raises** — it returns ``False`` when SMTP is unconfigured (empty `smtp_host`, logged as
a warning) or on any transport error, so callers stay best-effort. Uses the stdlib
``smtplib`` wrapped in ``asyncio.to_thread`` (no extra dependency), like the sync
firebase-admin wrapping in FcmGateway.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("izysafe.email")


class EmailGateway:
    async def send(
        self, to: str, subject: str, text: str, html: str | None = None
    ) -> bool:
        """Send an email. Returns True iff SMTP accepted it; never raises."""
        if not settings.smtp_host:
            logger.warning("SMTP not configured — skipping email to %s (subject=%r)", to, subject)
            return False
        return await asyncio.to_thread(self._send_sync, to, subject, text, html)

    def _send_sync(self, to: str, subject: str, text: str, html: str | None) -> bool:
        try:
            msg = EmailMessage()
            msg["From"] = settings.smtp_from
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(text)
            if html:
                msg.add_alternative(html, subtype="html")
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
            return True
        except Exception:  # smtplib/OSError — delivery is best-effort, never fatal
            logger.exception("Email send failed to %s", to)
            return False
