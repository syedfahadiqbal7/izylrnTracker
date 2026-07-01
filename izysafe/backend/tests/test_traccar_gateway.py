"""Unit tests for TraccarGateway (Sprint 5 Slice 1).

The endpoint tests cover wiring via the fake; these cover the real gateway's request
shape (URL, basic auth, custom-command body) and its fault-tolerance: it returns False
(never raises) when Traccar is unconfigured, rejects the command, or the network fails.
"""
from __future__ import annotations

import httpx
import pytest

from app.services import traccar_gateway as tg
from app.services.traccar_gateway import TraccarGateway


class _FakeResp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeClient:
    """Records the POST and returns a configured status; raises if `error` is set."""

    calls: list[dict] = []
    status_code = 200
    error: Exception | None = None

    def __init__(self, *args, **kwargs) -> None:
        self.init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False

    async def post(self, url, **kwargs):
        if _FakeClient.error is not None:
            raise _FakeClient.error
        _FakeClient.calls.append({"url": url, **kwargs})
        return _FakeResp(_FakeClient.status_code)


@pytest.fixture(autouse=True)
def _reset_and_configure(monkeypatch):
    _FakeClient.calls = []
    _FakeClient.status_code = 200
    _FakeClient.error = None
    monkeypatch.setattr(tg.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(tg.settings, "traccar_api_user", "admin@izysafe.local")
    monkeypatch.setattr(tg.settings, "traccar_api_password", "secret")
    monkeypatch.setattr(tg.settings, "traccar_url", "http://traccar:8082")
    yield


async def test_send_command_success_shape():
    ok = await TraccarGateway().send_command(7, "MONITOR,+919876543210#")
    assert ok is True
    call = _FakeClient.calls[0]
    assert call["url"] == "http://traccar:8082/api/commands"
    assert call["auth"] == ("admin@izysafe.local", "secret")
    assert call["json"] == {
        "deviceId": 7,
        "type": "custom",
        "description": "IzySafe command",
        "attributes": {"data": "MONITOR,+919876543210#"},
    }


async def test_send_command_includes_description():
    # Traccar queues commands for offline devices into a NOT NULL `description` column.
    await TraccarGateway().send_command(7, "MONITOR,+91#", description="IzySafe Sound Around")
    assert _FakeClient.calls[0]["json"]["description"] == "IzySafe Sound Around"


async def test_sound_around_uses_monitor_template(monkeypatch):
    monkeypatch.setattr(tg.settings, "traccar_monitor_template", "MONITOR,{phone}#")
    ok = await TraccarGateway().sound_around(7, "+919876543210")
    assert ok is True
    assert _FakeClient.calls[0]["json"]["attributes"]["data"] == "MONITOR,+919876543210#"


async def test_two_way_call_uses_callback_template(monkeypatch):
    monkeypatch.setattr(tg.settings, "traccar_callback_template", "CALLBACK,{phone}#")
    ok = await TraccarGateway().two_way_call(7, "+919876543210")
    assert ok is True
    assert _FakeClient.calls[0]["json"]["attributes"]["data"] == "CALLBACK,+919876543210#"


async def test_rejected_command_returns_false():
    _FakeClient.status_code = 400
    ok = await TraccarGateway().send_command(7, "MONITOR,+91#")
    assert ok is False


async def test_network_error_returns_false():
    _FakeClient.error = httpx.ConnectError("boom")
    ok = await TraccarGateway().send_command(7, "MONITOR,+91#")
    assert ok is False


async def test_unconfigured_returns_false_without_call(monkeypatch):
    monkeypatch.setattr(tg.settings, "traccar_api_user", "")
    monkeypatch.setattr(tg.settings, "traccar_api_password", "")
    ok = await TraccarGateway().send_command(7, "MONITOR,+91#")
    assert ok is False
    assert _FakeClient.calls == []  # short-circuited before any network call
