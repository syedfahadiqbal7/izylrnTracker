"""Test doubles shared across the suite."""
from __future__ import annotations


class FakeGateway:
    """Stand-in for OtpGateway: configurable success + call recording."""

    def __init__(self, whatsapp_ok: bool = True, sms_ok: bool = True) -> None:
        self.whatsapp_ok = whatsapp_ok
        self.sms_ok = sms_ok
        self.whatsapp_calls: list[tuple[str, str]] = []
        self.sms_calls: list[tuple[str, str]] = []
        self.last_otp: str | None = None

    async def send_whatsapp(self, phone: str, otp: str) -> bool:
        self.whatsapp_calls.append((phone, otp))
        self.last_otp = otp
        return self.whatsapp_ok

    async def send_sms(self, phone: str, otp: str) -> bool:
        self.sms_calls.append((phone, otp))
        self.last_otp = otp
        return self.sms_ok


class FakeInviteGateway:
    """Stand-in for InviteGateway: configurable channel + call recording."""

    def __init__(self, channel: str | None = "whatsapp") -> None:
        self.channel = channel          # set to None to simulate a delivery failure
        self.calls: list[tuple[str, str]] = []

    async def send_invite(self, phone: str, message: str) -> str | None:
        self.calls.append((phone, message))
        return self.channel


class FakeRealtimeGateway:
    """Stand-in for RealtimeGateway: records live-location writes."""

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok                                  # set False to simulate Firebase down
        self.calls: list[tuple[str, dict]] = []       # (child_id, payload)

    async def update_live_location(self, child_id: str, payload: dict) -> bool:
        self.calls.append((child_id, payload))
        return self.ok
