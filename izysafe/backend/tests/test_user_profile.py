"""Tests for PUT /auth/me (profile update) and PUT /auth/me/fcm-token."""
from __future__ import annotations

import pytest

ME = "/api/v1/auth/me"
FCM = "/api/v1/auth/me/fcm-token"


# --------------------------------------------------------------------------- #
# Happy paths
# --------------------------------------------------------------------------- #
async def test_update_full_profile(client, auth_headers, user, db_session):
    resp = await client.put(
        ME,
        headers=auth_headers,
        json={
            "name": "Aryan's Dad",
            "email": "dad@example.com",
            "language": "hi",
            "timezone": "Asia/Dubai",
            "quiet_hours_from": "22:00",
            "quiet_hours_to": "07:00",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["name"] == "Aryan's Dad"
    assert data["email"] == "dad@example.com"
    assert data["language"] == "hi"
    assert data["timezone"] == "Asia/Dubai"
    assert data["quiet_hours_from"] == "22:00:00"

    await db_session.refresh(user)
    assert user.language == "hi"
    assert user.email == "dad@example.com"


async def test_partial_update_preserves_other_fields(client, auth_headers, user, db_session):
    # user starts with name "Test Parent"; update only language
    resp = await client.put(ME, headers=auth_headers, json={"language": "ar"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["language"] == "ar"
    assert data["name"] == "Test Parent"   # untouched


async def test_get_me_reflects_update(client, auth_headers):
    await client.put(ME, headers=auth_headers, json={"name": "Updated Name"})
    resp = await client.get(ME, headers=auth_headers)
    assert resp.json()["data"]["name"] == "Updated Name"


async def test_set_fcm_token(client, auth_headers, user, db_session):
    resp = await client.put(FCM, headers=auth_headers, json={"fcm_token": "fcm-abc-123"})
    assert resp.status_code == 200
    assert resp.json()["data"]["success"] is True
    await db_session.refresh(user)
    assert user.fcm_token == "fcm-abc-123"


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
async def test_update_invalid_email(client, auth_headers):
    resp = await client.put(ME, headers=auth_headers, json={"email": "not-an-email"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_EMAIL"


async def test_update_invalid_timezone(client, auth_headers):
    resp = await client.put(ME, headers=auth_headers, json={"timezone": "Mars/Phobos"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_TIMEZONE"


@pytest.mark.parametrize("bad", [{"language": "fr"}, {"name": "A"}])
async def test_update_schema_validation(client, auth_headers, bad):
    # unsupported language / too-short name → Pydantic 422 envelope
    resp = await client.put(ME, headers=auth_headers, json=bad)
    assert resp.status_code == 422
    assert resp.json()["code"] == "VALIDATION_ERROR"


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
async def test_update_requires_auth(client):
    resp = await client.put(ME, json={"name": "Nobody"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_MISSING"


async def test_fcm_requires_auth(client):
    resp = await client.put(FCM, json={"fcm_token": "x"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_MISSING"
