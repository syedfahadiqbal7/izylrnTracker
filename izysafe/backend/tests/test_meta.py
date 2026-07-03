"""App-level meta: health probe + baseline security headers (prod-readiness)."""
from __future__ import annotations


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_security_headers_present(client):
    resp = await client.get("/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "permissions-policy" in resp.headers
    # HSTS is production-only (tests run with ENVIRONMENT=development).
    assert "strict-transport-security" not in resp.headers


async def test_docs_available_in_dev(client):
    assert (await client.get("/openapi.json")).status_code == 200
