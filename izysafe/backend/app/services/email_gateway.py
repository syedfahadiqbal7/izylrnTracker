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
        self,
        to: str,
        subject: str,
        text: str,
        html: str | None = None,
        smtp: dict | None = None,
    ) -> bool:
        """Send an email. Returns True iff SMTP accepted it; never raises.

        `smtp` optionally overrides the SMTP settings per field (used for admin-managed
        OTP email credentials); anything absent falls back to the environment settings,
        so existing callers (school emails, password reset) are unchanged.
        """
        smtp = smtp or {}
        host = smtp.get("host") or settings.smtp_host
        if not host:
            logger.warning("SMTP not configured — skipping email to %s (subject=%r)", to, subject)
            return False
        return await asyncio.to_thread(self._send_sync, to, subject, text, html, smtp)

    def _send_sync(
        self, to: str, subject: str, text: str, html: str | None, smtp: dict | None = None
    ) -> bool:
        smtp = smtp or {}
        host = smtp.get("host") or settings.smtp_host
        port = smtp.get("port") or settings.smtp_port
        user = smtp.get("user") or settings.smtp_user
        password = smtp.get("password") or settings.smtp_password
        sender = smtp.get("from_address") or settings.smtp_from
        use_tls = smtp["use_tls"] if smtp.get("use_tls") is not None else settings.smtp_use_tls
        try:
            msg = EmailMessage()
            msg["From"] = sender
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(text)
            if html:
                msg.add_alternative(html, subtype="html")
            with smtplib.SMTP(host, port, timeout=10) as server:
                if use_tls:
                    server.starttls()
                if user:
                    server.login(user, password)
                server.send_message(msg)
            return True
        except Exception:  # smtplib/OSError — delivery is best-effort, never fatal
            logger.exception("Email send failed to %s", to)
            return False
