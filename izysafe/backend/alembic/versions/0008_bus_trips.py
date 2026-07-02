"""bus trips + boardings + bus_boarded alert (Sprint 10 Slice 1b, driver actions)

Revision ID: 0008_bus_trips
Revises: 0007_driver_login
Create Date: Sprint 10

Durable trail for driver-run trips: `bus_trips` (one active per route via a partial
unique index) and `bus_boardings` (one per child per trip). Adds the `bus_boarded`
alert type for pickup confirmations. Idempotent — schema.sql (run by 0001) declares
these too, so a fresh `alembic upgrade head` no-ops here.
"""
from __future__ import annotations

from alembic import op

revision = "0008_bus_trips"
down_revision = "0007_driver_login"
branch_labels = None
depends_on = None

_ALERT_TYPES = (
    "sos,geofence_enter,geofence_exit,low_battery,critical_battery,device_offline,"
    "speed,watch_removed,route_deviation,pickup,school_arrival,school_absent,crash,"
    "anomaly,chat_reply,family_join,system,bus_arrival,bus_boarded"
)
_ALERT_LIST = ",".join(f"'{t}'" for t in _ALERT_TYPES.split(","))


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bus_trips (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            route_id    UUID NOT NULL REFERENCES bus_routes(id) ON DELETE CASCADE,
            driver_id   UUID REFERENCES drivers(id) ON DELETE SET NULL,
            status      VARCHAR(10) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active','ended')),
            started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at    TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_bus_trip_active_route "
        "ON bus_trips (route_id) WHERE status = 'active'"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_bus_trips_driver ON bus_trips (driver_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bus_boardings (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            trip_id     UUID NOT NULL REFERENCES bus_trips(id) ON DELETE CASCADE,
            child_id    UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
            stop_id     UUID REFERENCES bus_route_stops(id) ON DELETE SET NULL,
            boarded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (trip_id, child_id)
        )
        """
    )
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_type_check")
    op.execute(f"ALTER TABLE alerts ADD CONSTRAINT alerts_type_check CHECK (type IN ({_ALERT_LIST}))")


def downgrade() -> None:
    _old = _ALERT_LIST.replace(",'bus_boarded'", "")
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_type_check")
    op.execute(f"ALTER TABLE alerts ADD CONSTRAINT alerts_type_check CHECK (type IN ({_old}))")
    op.execute("DROP TABLE IF EXISTS bus_boardings")
    op.execute("DROP TABLE IF EXISTS bus_trips")
