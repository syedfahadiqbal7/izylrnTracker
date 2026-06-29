"""Unit tests for RealtimeGateway (Sprint 2, Slice 3).

The webhook tests cover wiring via the fake; these cover the real gateway's
fault-tolerance (no-op when Firebase is down) and the SDK call path (mocked).
"""
from __future__ import annotations

import sys
import types

import pytest

from app.services.realtime_gateway import RealtimeGateway


async def test_noop_when_firebase_not_ready(monkeypatch):
    monkeypatch.setattr("app.services.realtime_gateway.fb.is_ready", lambda: False)
    gw = RealtimeGateway()
    ok = await gw.update_live_location("child-1", {"lat": 1.0, "lng": 2.0})
    assert ok is False  # gracefully skipped, no exception


async def test_writes_to_reference_when_ready(monkeypatch):
    monkeypatch.setattr("app.services.realtime_gateway.fb.is_ready", lambda: True)

    calls: list[tuple[str, dict]] = []

    class _Ref:
        def __init__(self, path: str) -> None:
            self.path = path

        def set(self, payload: dict) -> None:
            calls.append((self.path, payload))

    # Inject a stub `firebase_admin.db` so the gateway's lazy import resolves it.
    fake_db = types.SimpleNamespace(reference=lambda path: _Ref(path))
    fake_firebase = types.ModuleType("firebase_admin")
    fake_firebase.db = fake_db
    monkeypatch.setitem(sys.modules, "firebase_admin", fake_firebase)

    gw = RealtimeGateway()
    ok = await gw.update_live_location("child-9", {"lat": 25.2, "lng": 55.3})

    assert ok is True
    assert calls == [("live_locations/child-9/latest", {"lat": 25.2, "lng": 55.3})]


async def test_returns_false_on_sdk_error(monkeypatch):
    monkeypatch.setattr("app.services.realtime_gateway.fb.is_ready", lambda: True)

    def _boom(path, payload):
        raise RuntimeError("firebase exploded")

    monkeypatch.setattr(RealtimeGateway, "_set", staticmethod(_boom))
    gw = RealtimeGateway()
    ok = await gw.update_live_location("child-2", {"lat": 1.0, "lng": 2.0})
    assert ok is False  # SDK error swallowed, ingestion unaffected
