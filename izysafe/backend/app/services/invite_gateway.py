"""Guardian-invite delivery: WhatsApp primary, SMS fallback.

Reuses the same MSG91/Twilio plumbing pattern as OtpGateway, but sends an invite
*link* (a different message/template) rather than a 6-digit code. Returns the
channel used, or None if every channel failed (the caller treats that as
non-fatal and surfaces a manual-share link).
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("izysafe.invite")


class InviteGateway:
    async def send_invite(self, phone: str, message: str) -> str | None:
        if await self._whatsapp(phone, message):
            return "whatsapp"
        if await self._sms(phone, message):
            return "sms"
        return None

    async def _whatsapp(self, phone: str, message: str) -> bool:
        # NOTE: production MSG91 WhatsApp requires an approved invite template;
        # wired fully in the integration pass. Free-text shown here for shape.
        if not settings.msg91_auth_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/",
                    headers={"authkey": settings.msg91_auth_key},
                    json={"recipient_number": phone.lstrip("+"), "text": message},
                )
                return resp.status_code < 300
        except httpx.HTTPError:
            logger.exception("WhatsApp invite send failed for %s", phone)
            return False

    async def _sms(self, phone: str, message: str) -> bool:
        if not (settings.twilio_sid and settings.twilio_token):
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_sid}/Messages.json",
                    auth=(settings.twilio_sid, settings.twilio_token),
                    data={"To": phone, "From": settings.twilio_from_number, "Body": message},
                )
                return resp.status_code < 300
        except httpx.HTTPError:
            logger.exception("SMS invite send failed for %s", phone)
            return False
