"""JWT denylist backed by Redis (logout / refresh-rotation revocation).

We store ONLY revoked token jtis, each with a TTL equal to the token's own
remaining lifetime, so the set is self-cleaning. Keys (CLAUDE.md §9):
    denylist:access:{jti}    TTL = access token remaining life  (<= 24h)
    denylist:refresh:{jti}   TTL = refresh token remaining life (<= 30d)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from redis.asyncio import Redis

TokenKind = Literal["access", "refresh"]


def _key(kind: TokenKind, jti: str) -> str:
    return f"denylist:{kind}:{jti}"


async def denylist(redis: Redis, kind: TokenKind, jti: str, exp_ts: int) -> None:
    """Revoke a token until it would have expired anyway. No-op if already expired."""
    ttl = int(exp_ts - datetime.now(timezone.utc).timestamp())
    if ttl > 0:
        await redis.set(_key(kind, jti), "1", ex=ttl)


async def is_denylisted(redis: Redis, kind: TokenKind, jti: str) -> bool:
    return bool(await redis.exists(_key(kind, jti)))
