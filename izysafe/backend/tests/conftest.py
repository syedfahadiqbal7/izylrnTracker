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

from app.api.deps import (
    get_battery_service,
    get_bus_tracking_service,
    get_chat_inbound_service,
    get_device_status_service,
    get_email_gateway,
    get_fcm_gateway,
    get_geocoding_gateway,
    get_geofence_breach_service,
    get_invite_gateway,
    get_otp_gateway,
    get_razorpay_gateway,
    get_realtime_gateway,
    get_route_deviation_service,
    get_sos_alarm_service,
    get_speed_service,
    get_stripe_gateway,
    get_traccar_gateway,
    get_watch_removed_service,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services.battery_service import BatteryService
from app.services.bus_tracking_service import BusTrackingService
from app.services.chat_service import ChatInboundService
from app.services.device_status import DeviceStatusService
from app.services.geofence_breach_service import GeofenceBreachService
from app.services.route_deviation_service import RouteDeviationService
from app.services.sos_service import SosAlarmService
from app.services.watch_removed_service import WatchRemovedService
from app.services.speed_service import SpeedService
from tests.fakes import (
    FakeEmailGateway,
    FakeFcmGateway,
    FakeGateway,
    FakeGeocodingGateway,
    FakeInviteGateway,
    FakeRazorpayGateway,
    FakeRealtimeGateway,
    FakeStripeGateway,
    FakeTraccarGateway,
)


class NonClosingSession:
    """Async context manager yielding the shared test session without closing it,
    so a service's `async with session_factory()` stays inside the test's
    savepoint/rollback isolation (shared by background tasks + lifespan loops)."""

    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc) -> bool:
        return False

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


@pytest.fixture
def fake_invite_gateway() -> FakeInviteGateway:
    return FakeInviteGateway()


@pytest.fixture
def fake_realtime_gateway() -> FakeRealtimeGateway:
    return FakeRealtimeGateway()


@pytest.fixture
def fake_fcm_gateway() -> FakeFcmGateway:
    return FakeFcmGateway()


@pytest.fixture
def fake_traccar_gateway() -> FakeTraccarGateway:
    return FakeTraccarGateway()


@pytest.fixture
def fake_geocoding_gateway() -> FakeGeocodingGateway:
    return FakeGeocodingGateway()


@pytest.fixture
def fake_email_gateway() -> FakeEmailGateway:
    return FakeEmailGateway()


@pytest.fixture
def fake_razorpay_gateway() -> FakeRazorpayGateway:
    return FakeRazorpayGateway()


@pytest.fixture
def fake_stripe_gateway() -> FakeStripeGateway:
    return FakeStripeGateway()


@pytest_asyncio.fixture
async def client(
    db_session, redis_client, fake_gateway, fake_invite_gateway,
    fake_realtime_gateway, fake_fcm_gateway, fake_traccar_gateway,
    fake_razorpay_gateway, fake_stripe_gateway, fake_geocoding_gateway,
    fake_email_gateway,
):
    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = lambda: redis_client
    app.dependency_overrides[get_otp_gateway] = lambda: fake_gateway
    app.dependency_overrides[get_invite_gateway] = lambda: fake_invite_gateway
    app.dependency_overrides[get_realtime_gateway] = lambda: fake_realtime_gateway
    app.dependency_overrides[get_fcm_gateway] = lambda: fake_fcm_gateway
    app.dependency_overrides[get_traccar_gateway] = lambda: fake_traccar_gateway
    app.dependency_overrides[get_geocoding_gateway] = lambda: fake_geocoding_gateway
    app.dependency_overrides[get_email_gateway] = lambda: fake_email_gateway
    app.dependency_overrides[get_razorpay_gateway] = lambda: fake_razorpay_gateway
    app.dependency_overrides[get_stripe_gateway] = lambda: fake_stripe_gateway
    # Services whose work runs in a BackgroundTask (after the request session would
    # have closed) are bound to the isolated test session + fake FCM.
    app.dependency_overrides[get_device_status_service] = lambda: DeviceStatusService(
        lambda: NonClosingSession(db_session), redis_client
    )
    app.dependency_overrides[get_battery_service] = lambda: BatteryService(
        lambda: NonClosingSession(db_session), redis_client, fake_fcm_gateway
    )
    app.dependency_overrides[get_speed_service] = lambda: SpeedService(
        lambda: NonClosingSession(db_session), redis_client, fake_fcm_gateway
    )
    app.dependency_overrides[get_geofence_breach_service] = lambda: GeofenceBreachService(
        lambda: NonClosingSession(db_session), redis_client, fake_fcm_gateway
    )
    app.dependency_overrides[get_route_deviation_service] = lambda: RouteDeviationService(
        lambda: NonClosingSession(db_session), redis_client, fake_fcm_gateway
    )
    app.dependency_overrides[get_sos_alarm_service] = lambda: SosAlarmService(
        lambda: NonClosingSession(db_session), redis_client,
        fake_realtime_gateway, fake_fcm_gateway,
    )
    app.dependency_overrides[get_watch_removed_service] = lambda: WatchRemovedService(
        lambda: NonClosingSession(db_session), redis_client, fake_fcm_gateway
    )
    app.dependency_overrides[get_chat_inbound_service] = lambda: ChatInboundService(
        lambda: NonClosingSession(db_session), fake_fcm_gateway
    )
    app.dependency_overrides[get_bus_tracking_service] = lambda: BusTrackingService(
        lambda: NonClosingSession(db_session), redis_client, fake_fcm_gateway
    )

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
