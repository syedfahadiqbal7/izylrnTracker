"""Shared test fixtures.

Isolation strategy:
  * DB: bind an AsyncSession to a single connection inside an outer transaction
    using join_transaction_mode="create_savepoint", so the service's commit()
    only releases a savepoint; the outer transaction is rolled back after each
    test → the database is left pristine.
  * Redis: fakeredis (in-memory, async).
  * OTP gateway: a FakeGateway with configurable success + call recording.
"""
from __future__ import annotations

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_otp_gateway
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from tests.fakes import FakeGateway

# NullPool: never reuse an asyncpg connection across pytest-asyncio's
# function-scoped event loops (each test gets a fresh connection on its own loop).
_engine = create_async_engine(settings.database_url, poolclass=NullPool)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture
async def db_session():
    async with _engine.connect() as conn:
        await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


@pytest_asyncio.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.flushall()
        await client.aclose()


@pytest.fixture
def fake_gateway() -> FakeGateway:
    return FakeGateway()


@pytest_asyncio.fixture
async def client(db_session, redis_client, fake_gateway):
    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = lambda: redis_client
    app.dependency_overrides[get_otp_gateway] = lambda: fake_gateway

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user(db_session) -> User:
    """A persisted parent user (shared across auth/profile tests)."""
    u = User(phone="+919876543210", country_code="+91", name="Test Parent")
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.fixture
def auth_headers(user) -> dict[str, str]:
    """Authorization header carrying a valid access token for `user`."""
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
