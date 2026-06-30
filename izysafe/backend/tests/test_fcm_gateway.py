"""Unit tests for FcmGateway (Sprint 2, Slice 4) — fault tolerance + SDK path."""
from __future__ import annotations

import sys
import types

from app.services.fcm_gateway import FcmGateway


async def test_noop_when_no_tokens(monkeypatch):
    monkeypatch.setattr("app.services.fcm_gateway.fb.is_ready", lambda: True)
    assert await FcmGateway().send([], "t", "b") == 0


async def test_noop_when_firebase_not_ready(monkeypatch):
    monkeypatch.setattr("app.services.fcm_gateway.fb.is_ready", lambda: False)
    assert await FcmGateway().send(["tok"], "t", "b") == 0


async def test_sends_multicast_when_ready(monkeypatch):
    monkeypatch.setattr("app.services.fcm_gateway.fb.is_ready", lambda: True)
    captured = {}

    class _Resp:
        success_count = 2

    def _send_each_for_multicast(msg):
        captured["msg"] = msg
        return _Resp()

    fake_messaging = types.SimpleNamespace(
        MulticastMessage=lambda **kw: kw,
        Notification=lambda **kw: kw,
        send_each_for_multicast=_send_each_for_multicast,
    )
    fake_module = types.ModuleType("firebase_admin")
    fake_module.messaging = fake_messaging
    monkeypatch.setitem(sys.modules, "firebase_admin", fake_module)

    n = await FcmGateway().send(["a", "b"], "Title", "Body", {"k": 1, "type": "x"})
    assert n == 2
    assert captured["msg"]["tokens"] == ["a", "b"]
    assert captured["msg"]["data"] == {"k": "1", "type": "x"}  # all stringified


async def test_returns_zero_on_sdk_error(monkeypatch):
    monkeypatch.setattr("app.services.fcm_gateway.fb.is_ready", lambda: True)

    def _boom(tokens, title, body, data):
        raise RuntimeError("fcm exploded")

    monkeypatch.setattr(FcmGateway, "_send_multicast", staticmethod(_boom))
    assert await FcmGateway().send(["tok"], "t", "b") == 0
