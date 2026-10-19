"""OTP delivery gateway: MSG91 WhatsApp + Twilio SMS + SMTP Email.

Real network calls live here so they can be cleanly swapped for a fake in tests
(the endpoint resolves the gateway via a FastAPI dependency that tests override).
Each method returns True on confirmed delivery, False otherwise — the service
layer decides the channel order / when to fall back. Methods never raise on
provider errors. Email reuses the shared EmailGateway (SMTP), which no-ops when
unconfigured — matching the WhatsApp/SMS "unconfigured ⇒ False" seam.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings
from app.services.email_gateway import EmailGateway

logger = logging.getLogger("izysafe.otp")

OTP_MESSAGE = "{otp} is your IzySafe verification code — valid for 10 minutes — do not share with anyone"
OTP_EMAIL_SUBJECT = "Your IzySafe verification code"


class OtpGateway:
    """Default production gateway. Construct once per request (cheap)."""

    def __init__(self, email_gateway: EmailGateway | None = None) -> None:
        # Reuse the shared SMTP gateway for Email OTP (no-op when unconfigured).
        self._email = email_gateway or EmailGateway()

    async def send_whatsapp(self, phone: str, otp: str) -> bool:
        if not settings.msg91_auth_key:
            logger.warning("MSG91 not configured — cannot send WhatsApp OTP.")
            return False
        try:
            async with httpx.AsyncClient(timeout=settings.whatsapp_fallback_seconds) as client:
                resp = await client.post(
                    "https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/",
                    headers={"authkey": settings.msg91_auth_key},
                    json={
                        "integrated_number": settings.twilio_from_number,
                        "recipient_number": phone.lstrip("+"),
                        "content_type": "template",
                        "template": {
                            "name": settings.msg91_whatsapp_template,
                            "components": {"body_1": {"type": "text", "value": otp}},
                        },
                    },
                )
                return resp.status_code < 300
        except httpx.HTTPError:
            logger.exception("WhatsApp OTP send failed for %s", phone)
            return False

    async def send_sms(self, phone: str, otp: str) -> bool:
        if not (settings.twilio_sid and settings.twilio_token):
            logger.warning("Twilio not configured — cannot send SMS OTP.")
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_sid}/Messages.json",
                    auth=(settings.twilio_sid, settings.twilio_token),
                    data={
                        "To": phone,
                        "From": settings.twilio_from_number,
                        "Body": OTP_MESSAGE.format(otp=otp),
                    },
                )
                return resp.status_code < 300
        except httpx.HTTPError:
            logger.exception("SMS OTP send failed for %s", phone)
            return False

    async def send_email(self, email: str, otp: str) -> bool:
        """Email the OTP via the shared EmailGateway. Returns False (never raises)
        when SMTP is unconfigured or delivery fails — the subject carries no code,
        so the OTP never lands in a log line."""
        return await self._email.send(
            to=email,
            subject=OTP_EMAIL_SUBJECT,
            text=OTP_MESSAGE.format(otp=otp),
        )
