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
        self.sos_cleared: list[str] = []              # child_ids resolved

    async def update_live_location(self, child_id: str, payload: dict) -> bool:
        self.calls.append((child_id, payload))
        return self.ok

    async def set_sos(self, child_id: str, payload: dict) -> bool:
        self.sos_calls.append((child_id, payload))
        return self.ok

    async def clear_sos(self, child_id: str) -> bool:
        self.sos_cleared.append(child_id)
        return self.ok


class FakeTraccarGateway:
    """Stand-in for TraccarGateway: records dispatched commands, returns configurable ok."""

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok  # set False to simulate a rejected/failed command
        self.calls: list[dict] = []                   # {traccar_id, data} for send_command
        self.sound_around_calls: list[tuple[int, str]] = []   # (traccar_id, phone)
        self.two_way_calls: list[tuple[int, str]] = []        # (traccar_id, phone)

    async def send_command(
        self, traccar_id: int, data: str, description: str = "IzySafe command"
    ) -> bool:
        self.calls.append({"traccar_id": traccar_id, "data": data, "description": description})
        return self.ok

    async def sound_around(self, traccar_id: int, phone: str) -> bool:
        self.sound_around_calls.append((traccar_id, phone))
        return await self.send_command(traccar_id, f"MONITOR,{phone}#")

    async def two_way_call(self, traccar_id: int, phone: str) -> bool:
        self.two_way_calls.append((traccar_id, phone))
        return await self.send_command(traccar_id, f"CALLBACK,{phone}#")


class FakeRazorpayGateway:
    """Stand-in for RazorpayGateway.create_subscription. verify_webhook stays the real
    static (tests exercise the actual HMAC path)."""

    def __init__(self, sub: dict | None = None, fail: bool = False) -> None:
        self.fail = fail
        self.sub = sub or {
            "id": "sub_TEST123", "short_url": "https://rzp.io/i/test", "status": "created",
        }
        self.calls: list[dict] = []

    async def create_subscription(self, plan_id: str, notes: dict, total_count: int):
        self.calls.append({"plan_id": plan_id, "notes": notes, "total_count": total_count})
        return None if self.fail else self.sub


class FakeStripeGateway:
    """Stand-in for StripeGateway.create_checkout_session. verify_webhook stays the real
    static (tests exercise the actual HMAC path)."""

    def __init__(self, session: dict | None = None, fail: bool = False) -> None:
        self.fail = fail
        self.session = session or {
            "id": "cs_test_123", "url": "https://checkout.stripe.com/pay/cs_test_123",
            "status": "open",
        }
        self.calls: list[dict] = []

    async def create_checkout_session(
        self, price_id: str, metadata: dict, success_url: str, cancel_url: str
    ):
        self.calls.append({
            "price_id": price_id, "metadata": metadata,
            "success_url": success_url, "cancel_url": cancel_url,
        })
        return None if self.fail else self.session


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
