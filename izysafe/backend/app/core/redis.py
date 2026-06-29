"""Async Redis client (singleton).

Holds live location cache, geofence state, online TTLs, rate limiters, and the
batch:locations write buffer. See CLAUDE.md §9 for the full key reference.
"""
from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.core.config import settings

# decode_responses=True → str in/out (we JSON-encode values at the call site).
redis_client: Redis = from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
    health_check_interval=30,
)


async def get_redis() -> Redis:
    """FastAPI dependency returning the shared client."""
    return redis_client


async def close_redis() -> None:
    await redis_client.aclose()
