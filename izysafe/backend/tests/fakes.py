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
    """Stand-in for RealtimeGateway: records live-location + SOS writes."""

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok                                  # set False to simulate Firebase down
        self.calls: list[tuple[str, dict]] = []       # (child_id, payload)
        self.sos_calls: list[tuple[str, dict]] = []   # (child_id, sos payload)

    async def update_live_location(self, child_id: str, payload: dict) -> bool:
        self.calls.append((child_id, payload))
        return self.ok

    async def set_sos(self, child_id: str, payload: dict) -> bool:
        self.sos_calls.append((child_id, payload))
        return self.ok


class FakeFcmGateway:
    """Stand-in for FcmGateway: records multicast sends, returns token count."""

    def __init__(self) -> None:
        self.calls: list[dict] = []  # {tokens, title, body, data, urgent}

    async def send(self, tokens, title, body, data=None, urgent=False) -> int:
        self.calls.append({
            "tokens": list(tokens), "title": title, "body": body,
            "data": data, "urgent": urgent,
        })
        return len(tokens)
