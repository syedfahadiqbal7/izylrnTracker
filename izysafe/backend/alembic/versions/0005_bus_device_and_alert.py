"""bus device_type + bus_arrival alert type (Sprint 8, F28 bus tracking)

Revision ID: 0005_bus_device_and_alert
Revises: 0004_attendance_links
Create Date: Sprint 8

Widens two CHECK constraints so a bus GPS tracker can be a `devices` row
(device_type='bus') and the stop-arrival notification (Slice 5) has an alert type.
Both are DROP-then-ADD by the DB's auto-generated constraint names, guarded with
IF EXISTS so a fresh `alembic upgrade head` (which runs the updated schema.sql, then
this) is idempotent.
"""
from __future__ import annotations

from alembic import op

revision = "0005_bus_device_and_alert"
down_revision = "0004_attendance_links"
branch_labels = None
depends_on = None

_ALERT_TYPES = (
    "sos,geofence_enter,geofence_exit,low_battery,critical_battery,device_offline,"
    "speed,watch_removed,route_deviation,pickup,school_arrival,school_absent,crash,"
    "anomaly,chat_reply,family_join,system,bus_arrival"
)
_ALERT_LIST = ",".join(f"'{t}'" for t in _ALERT_TYPES.split(","))


def upgrade() -> None:
    op.execute("ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_device_type_check")
    op.execute(
        "ALTER TABLE devices ADD CONSTRAINT devices_device_type_check "
        "CHECK (device_type IN ('watch','bag_tracker','phone','bus'))"
    )
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_type_check")
    op.execute(f"ALTER TABLE alerts ADD CONSTRAINT alerts_type_check CHECK (type IN ({_ALERT_LIST}))")


def downgrade() -> None:
    op.execute("ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_device_type_check")
    op.execute(
        "ALTER TABLE devices ADD CONSTRAINT devices_device_type_check "
        "CHECK (device_type IN ('watch','bag_tracker','phone'))"
    )
    _old = _ALERT_LIST.replace(",'bus_arrival'", "")
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_type_check")
    op.execute(f"ALTER TABLE alerts ADD CONSTRAINT alerts_type_check CHECK (type IN ({_old}))")
