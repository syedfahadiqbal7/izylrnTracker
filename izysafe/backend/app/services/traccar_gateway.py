"""Traccar outbound command gateway — the audio path of Flow F11/F12 (CLAUDE.md §3.12).

There is **no media server**: Sound Around (F11) and Two-way Call (F12) work by issuing
a SIM command to the watch through Traccar's command API. The watch then dials the
parent's phone over its own SIM — `MONITOR,<phone>#` for a silent ambient listen,
`CALLBACK,<phone>#` for a duplex call. The backend only *issues the command + logs +
gates*; the actual audio never touches our servers.

Mirrors the other external gateways (OtpGateway/Realtime/Fcm): the real network call
lives here so tests can swap a fake via a FastAPI dependency override. Methods **never
raise** on provider errors — they return ``True`` only when Traccar accepts the command
(HTTP < 300), ``False`` otherwise (not configured / rejected / network error), so the
caller decides how to surface a dispatch failure.

NB (hardware caveat, docs/HARDWARE_SPIKE.md §4): the command *strings* are GT06-model-
specific and unvalidated end-to-end; whether the watch actually rings / answers / hangs
up is **not observable** from the backend. We log only that the command was dispatched.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("izysafe.traccar")


class TraccarGateway:
    """Default production gateway. Construct once per request (cheap)."""

    async def send_command(
        self, traccar_id: int, data: str, description: str = "IzySafe command"
    ) -> bool:
        """POST a custom command to Traccar for the given device. Returns True iff
        Traccar accepts it (HTTP < 300). Never raises.

        ``description`` is required: when the device is offline Traccar *queues* the
        command into ``tc_commands`` (a NOT NULL column), so omitting it yields a
        400 even though we only dispatch to online watches (verified against Traccar)."""
        if not (settings.traccar_api_user and settings.traccar_api_password):
            logger.warning("Traccar API not configured — cannot command device %s", traccar_id)
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{settings.traccar_url}/api/commands",
                    auth=(settings.traccar_api_user, settings.traccar_api_password),
                    json={
                        "deviceId": traccar_id,
                        "type": "custom",
                        "description": description,
                        "attributes": {"data": data},
                    },
                )
        except httpx.HTTPError:
            logger.exception("Traccar command failed for device %s", traccar_id)
            return False
        if resp.status_code >= 300:
            logger.warning(
                "Traccar rejected command for device %s (HTTP %s)", traccar_id, resp.status_code
            )
            return False
        return True

    async def sound_around(self, traccar_id: int, phone: str) -> bool:
        """Sound Around (F11): tell the watch to silently call `phone` for ambient audio."""
        return await self.send_command(
            traccar_id,
            settings.traccar_monitor_template.format(phone=phone),
            description="IzySafe Sound Around",
        )

    async def two_way_call(self, traccar_id: int, phone: str) -> bool:
        """Two-way Call (F12, Slice 2): tell the watch to dial `phone` for a duplex call."""
        return await self.send_command(
            traccar_id,
            settings.traccar_callback_template.format(phone=phone),
            description="IzySafe Two-way Call",
        )
