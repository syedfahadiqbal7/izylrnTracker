"""Tests for the public live-tracking PAGE (Share Links, F22).

The page itself is a static, login-less HTML shell (root path `/track/{token}`, not under
`/api/v1`) that resolves the token client-side against the public JSON API. These tests
pin its contract: served without auth, correct content type, and — critically — the token
is NOT reflected into the HTML (no server-side interpolation → no XSS surface).
"""
from __future__ import annotations


async def test_track_page_served_as_html_without_auth(client):
    resp = await client.get("/track/anytoken")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "izy" in body and "Lrn" in body  # branded shell
    assert "leaflet" in body.lower()          # map library present
    assert "/api/v1/share/" in body           # polls the public JSON endpoint


async def test_track_page_does_not_reflect_token(client):
    # The token is read from the URL by the page's own JS, never interpolated server-side,
    # so an attacker-controlled token can't appear in (and thus can't inject into) the HTML.
    resp = await client.get("/track/INJECTME_UNIQUE_12345")
    assert resp.status_code == 200
    assert "INJECTME_UNIQUE_12345" not in resp.text


async def test_track_page_is_not_under_api_v1(client):
    # The versioned API namespace must not accidentally shadow / expose the page.
    resp = await client.get("/api/v1/track/anytoken")
    assert resp.status_code == 404
