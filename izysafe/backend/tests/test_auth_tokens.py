"""Tests for /auth/refresh, /auth/logout, and the get_current_user dependency
(exercised via GET /auth/me)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token

PHONE = "+919876543210"


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _expired_token(user_id: str, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "type": token_type,
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
            "jti": "expired-jti",
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


# --------------------------------------------------------------------------- #
# /auth/refresh
# --------------------------------------------------------------------------- #
async def test_refresh_rotates_tokens(client, user):
    old_refresh = create_refresh_token(str(user.id))
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert decode_token(data["access_token"], expected_type="access")["sub"] == str(user.id)
    # rotation issues a brand-new refresh token
    assert data["refresh_token"] != old_refresh


async def test_refresh_old_token_revoked_after_rotation(client, user):
    old_refresh = create_refresh_token(str(user.id))
    ok = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert ok.status_code == 200
    # reusing the rotated-out refresh token must now fail
    reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse.status_code == 401
    assert reuse.json()["code"] == "TOKEN_REVOKED"


async def test_refresh_rejects_access_token(client, user):
    access = create_access_token(str(user.id))
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_INVALID"


async def test_refresh_rejects_garbage(client):
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not.a.jwt"})
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_INVALID"


async def test_refresh_expired(client, user):
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": _expired_token(str(user.id), "refresh")}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_EXPIRED"


# --------------------------------------------------------------------------- #
# get_current_user via GET /auth/me
# --------------------------------------------------------------------------- #
async def test_me_success(client, user):
    access = create_access_token(str(user.id))
    resp = await client.get("/api/v1/auth/me", headers=_auth_header(access))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["id"] == str(user.id)
    assert data["phone"] == PHONE


async def test_me_missing_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_MISSING"


async def test_me_garbage_token(client):
    resp = await client.get("/api/v1/auth/me", headers=_auth_header("not.a.jwt"))
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_INVALID"


async def test_me_expired_token(client, user):
    resp = await client.get(
        "/api/v1/auth/me", headers=_auth_header(_expired_token(str(user.id), "access"))
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_EXPIRED"


async def test_me_refresh_token_rejected(client, user):
    # a refresh token must not authenticate as an access token
    refresh = create_refresh_token(str(user.id))
    resp = await client.get("/api/v1/auth/me", headers=_auth_header(refresh))
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_INVALID"


async def test_me_unknown_user(client):
    # validly-signed token for a user id that doesn't exist
    access = create_access_token("00000000-0000-0000-0000-000000000000")
    resp = await client.get("/api/v1/auth/me", headers=_auth_header(access))
    assert resp.status_code == 401
    assert resp.json()["code"] == "USER_NOT_FOUND"


# --------------------------------------------------------------------------- #
# /auth/logout
# --------------------------------------------------------------------------- #
async def test_logout_revokes_both_tokens(client, user):
    access = create_access_token(str(user.id))
    refresh = create_refresh_token(str(user.id))

    # logout requires auth (the access token) + the refresh token in the body
    out = await client.request(
        "DELETE", "/api/v1/auth/logout",
        headers=_auth_header(access),
        json={"refresh_token": refresh},
    )
    assert out.status_code == 200
    assert out.json()["data"]["success"] is True

    # the access token is now denylisted → /me rejects it
    me = await client.get("/api/v1/auth/me", headers=_auth_header(access))
    assert me.status_code == 401
    assert me.json()["code"] == "TOKEN_REVOKED"

    # the refresh token is denylisted → /refresh rejects it
    ref = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert ref.status_code == 401
    assert ref.json()["code"] == "TOKEN_REVOKED"


async def test_logout_requires_auth(client, user):
    resp = await client.request(
        "DELETE", "/api/v1/auth/logout",
        json={"refresh_token": create_refresh_token(str(user.id))},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "TOKEN_MISSING"
