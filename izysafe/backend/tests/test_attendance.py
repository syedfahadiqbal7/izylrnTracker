"""Tests for Attendance (Sprint 8 Slice 3, F27).

Covers the write engine (arrival classification, window/opt-in gates, exit hours,
manual-preserve, absent→arrival upgrade), the daily absent sweep (school-day/holiday/
window/opt-in gates + idempotency), the admin API (link-zone, daily register, history,
manual override, tenant isolation), and the geofence-transition → attendance wiring.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import select

from app.core.security import create_access_token, hash_secret
from app.models.child import Child, FamilyMember
from app.models.location import Geofence
from app.models.school import AttendanceRecord, School, SchoolAdmin, StudentEnrollment
from app.models.user import User
from app.services.attendance_service import AttendanceEngine
from app.services.geofence_breach_service import GeofenceBreachService
from tests.conftest import NonClosingSession
from tests.fakes import FakeFcmGateway

STUDENTS = "/api/v1/schools/students"

# Fixed Wednesday. tz=UTC school; window 07:00, on_time 09:00, late 11:00.
DAY = date(2026, 6, 17)
ON_TIME = datetime(2026, 6, 17, 8, 30, tzinfo=timezone.utc)   # in window, <=09:00
LATE = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)      # <=11:00, >09:00
BEFORE_WINDOW = datetime(2026, 6, 17, 5, 0, tzinfo=timezone.utc)
EXIT_AT = datetime(2026, 6, 17, 15, 0, tzinfo=timezone.utc)
AFTER_LATE = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)  # sweep instant

CLAT, CLNG = 18.5204, 73.8567
INSIDE = (18.5204, 73.8567)
OUTSIDE = (19.0, 74.0)
ALL_DAYS = [1, 2, 3, 4, 5, 6, 7]


async def _setup(db, *, tz="UTC", school_days=None, opt_in=True, linked=True, holidays=None):
    school = School(
        name="Green Valley", timezone=tz, holidays=holidays,
        on_time_before=time(9, 0), late_until=time(11, 0), arrival_window_from=time(7, 0),
        school_days=(school_days or ALL_DAYS),
    )
    db.add(school)
    await db.flush()
    admin = SchoolAdmin(
        school_id=school.id, email=f"a-{uuid.uuid4().hex[:8]}@s.test",
        password_hash=hash_secret("password123"), role="admin", active=True,
    )
    db.add(admin)
    parent = User(phone="+9198" + f"{uuid.uuid4().int % 10**8:08d}", country_code="+91")
    db.add(parent)
    await db.flush()
    child = Child(name="Aryan")
    db.add(child)
    await db.flush()
    db.add(FamilyMember(
        child_id=child.id, user_id=parent.id, role="parent",
        is_primary=True, can_view=True, can_call=True, can_manage=True,
    ))
    db.add(StudentEnrollment(
        school_id=school.id, child_id=child.id, class_grade="5A", parent_opt_in=opt_in,
    ))
    fence = Geofence(
        child_id=child.id, name="School", zone_type="school", type="circle",
        center_lat=CLAT, center_lng=CLNG, radius_m=200, active_days=ALL_DAYS,
        school_id=(school.id if linked else None),
    )
    db.add(fence)
    await db.flush()
    hdr = {"Authorization": f"Bearer {create_access_token(str(admin.id), extra={'scope': 'school_admin'})}"}
    return school, admin, child, fence, hdr


def _engine(db):
    return AttendanceEngine(lambda: NonClosingSession(db))


async def _rec(db, school_id, child_id, day=DAY):
    return (
        await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.school_id == school_id,
                AttendanceRecord.child_id == child_id,
                AttendanceRecord.date == day,
            )
        )
    ).scalar_one_or_none()


# --------------------------------------------------------------------------- #
# Engine: record_transition
# --------------------------------------------------------------------------- #
async def test_arrival_on_time(db_session):
    school, _, child, _, _ = await _setup(db_session)
    await _engine(db_session).record_transition(child.id, school.id, "enter", ON_TIME)
    rec = await _rec(db_session, school.id, child.id)
    assert rec.status == "on_time" and rec.arrival_time is not None


async def test_arrival_late(db_session):
    school, _, child, _, _ = await _setup(db_session)
    await _engine(db_session).record_transition(child.id, school.id, "enter", LATE)
    assert (await _rec(db_session, school.id, child.id)).status == "late"


async def test_arrival_before_window_ignored(db_session):
    school, _, child, _, _ = await _setup(db_session)
    await _engine(db_session).record_transition(child.id, school.id, "enter", BEFORE_WINDOW)
    assert await _rec(db_session, school.id, child.id) is None


async def test_exit_sets_departure_and_hours(db_session):
    school, _, child, _, _ = await _setup(db_session)
    eng = _engine(db_session)
    await eng.record_transition(child.id, school.id, "enter", ON_TIME)
    await eng.record_transition(child.id, school.id, "exit", EXIT_AT)
    rec = await _rec(db_session, school.id, child.id)
    assert rec.departure_time is not None
    assert rec.total_hours == 6.5


async def test_no_optin_no_attendance(db_session):
    school, _, child, _, _ = await _setup(db_session, opt_in=False)
    await _engine(db_session).record_transition(child.id, school.id, "enter", ON_TIME)
    assert await _rec(db_session, school.id, child.id) is None


async def test_manual_record_not_overwritten(db_session):
    school, _, child, _, _ = await _setup(db_session)
    db_session.add(AttendanceRecord(
        school_id=school.id, child_id=child.id, date=DAY, status="absent", marked_manually=True,
    ))
    await db_session.flush()
    await _engine(db_session).record_transition(child.id, school.id, "enter", ON_TIME)
    rec = await _rec(db_session, school.id, child.id)
    assert rec.status == "absent" and rec.arrival_time is None  # manual preserved


async def test_absent_then_arrival_upgrades(db_session):
    school, _, child, _, _ = await _setup(db_session)
    db_session.add(AttendanceRecord(
        school_id=school.id, child_id=child.id, date=DAY, status="absent",
    ))
    await db_session.flush()
    await _engine(db_session).record_transition(child.id, school.id, "enter", ON_TIME)
    rec = await _rec(db_session, school.id, child.id)
    assert rec.status == "on_time" and rec.arrival_time is not None


# --------------------------------------------------------------------------- #
# Engine: absent sweep
# --------------------------------------------------------------------------- #
async def test_sweep_marks_absent(db_session):
    school, _, child, _, _ = await _setup(db_session)
    marked = await _engine(db_session).sweep_absent(AFTER_LATE)
    assert marked == 1
    assert (await _rec(db_session, school.id, child.id)).status == "absent"


async def test_sweep_skips_before_late_until(db_session):
    school, _, child, _, _ = await _setup(db_session)
    assert await _engine(db_session).sweep_absent(ON_TIME) == 0  # 08:30 < 11:00


async def test_sweep_skips_holiday(db_session):
    school, _, child, _, _ = await _setup(db_session, holidays=[DAY.isoformat()])
    assert await _engine(db_session).sweep_absent(AFTER_LATE) == 0


async def test_sweep_skips_non_school_day(db_session):
    # DAY is a Wednesday (isoweekday 3); exclude it.
    school, _, child, _, _ = await _setup(db_session, school_days=[1, 2, 4, 5])
    assert await _engine(db_session).sweep_absent(AFTER_LATE) == 0


async def test_sweep_skips_not_opted_in(db_session):
    school, _, child, _, _ = await _setup(db_session, opt_in=False)
    assert await _engine(db_session).sweep_absent(AFTER_LATE) == 0


async def test_sweep_skips_present_child(db_session):
    school, _, child, _, _ = await _setup(db_session)
    await _engine(db_session).record_transition(child.id, school.id, "enter", ON_TIME)
    marked = await _engine(db_session).sweep_absent(AFTER_LATE)
    assert marked == 0
    assert (await _rec(db_session, school.id, child.id)).status == "on_time"


async def test_sweep_idempotent(db_session):
    school, _, child, _, _ = await _setup(db_session)
    eng = _engine(db_session)
    assert await eng.sweep_absent(AFTER_LATE) == 1
    assert await eng.sweep_absent(AFTER_LATE) == 0  # already marked


# --------------------------------------------------------------------------- #
# Geofence-transition wiring
# --------------------------------------------------------------------------- #
async def test_geofence_enter_records_attendance(db_session, redis_client):
    school, _, child, _, _ = await _setup(db_session)
    svc = GeofenceBreachService(lambda: NonClosingSession(db_session), redis_client, FakeFcmGateway())
    await svc.check_all_fences(child.id, *OUTSIDE, now=ON_TIME)   # baseline outside
    await svc.check_all_fences(child.id, *INSIDE, now=ON_TIME)    # enter school zone
    rec = await _rec(db_session, school.id, child.id)
    assert rec is not None and rec.status == "on_time"


async def test_geofence_unlinked_zone_no_attendance(db_session, redis_client):
    # A school zone NOT linked to the school (school_id NULL) → no attendance.
    school, _, child, _, _ = await _setup(db_session, linked=False)
    svc = GeofenceBreachService(lambda: NonClosingSession(db_session), redis_client, FakeFcmGateway())
    await svc.check_all_fences(child.id, *OUTSIDE, now=ON_TIME)
    await svc.check_all_fences(child.id, *INSIDE, now=ON_TIME)
    assert await _rec(db_session, school.id, child.id) is None


# --------------------------------------------------------------------------- #
# Admin API
# --------------------------------------------------------------------------- #
async def _enrollment_id(db, child_id):
    return str((await db.execute(select(StudentEnrollment).where(StudentEnrollment.child_id == child_id))).scalar_one().id)


async def test_link_zone(client, db_session):
    school, _, child, fence, hdr = await _setup(db_session, linked=False)
    eid = await _enrollment_id(db_session, child.id)
    resp = await client.post(f"{STUDENTS}/{eid}/attendance-zone", headers=hdr)
    assert resp.status_code == 201, resp.text
    await db_session.refresh(fence)
    assert fence.school_id == school.id


async def test_link_zone_no_school_zone(client, db_session):
    school, admin, child, fence, hdr = await _setup(db_session, linked=False)
    fence.zone_type = "home"  # no school zone remains
    await db_session.flush()
    eid = await _enrollment_id(db_session, child.id)
    resp = await client.post(f"{STUDENTS}/{eid}/attendance-zone", headers=hdr)
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_SCHOOL_ZONE"


async def test_daily_register(client, db_session):
    school, _, child, _, hdr = await _setup(db_session)
    await _engine(db_session).record_transition(child.id, school.id, "enter", ON_TIME)
    resp = await client.get(f"/api/v1/schools/attendance?date={DAY.isoformat()}", headers=hdr)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["status"] == "on_time"
    assert data[0]["child_name"] == "Aryan"


async def test_daily_register_unknown_when_no_record(client, db_session):
    school, _, child, _, hdr = await _setup(db_session)
    resp = await client.get(f"/api/v1/schools/attendance?date={DAY.isoformat()}", headers=hdr)
    assert resp.json()["data"][0]["status"] == "unknown"


async def test_child_history(client, db_session):
    school, _, child, _, hdr = await _setup(db_session)
    await _engine(db_session).record_transition(child.id, school.id, "enter", ON_TIME)
    eid = await _enrollment_id(db_session, child.id)
    resp = await client.get(
        f"{STUDENTS}/{eid}/attendance?from={DAY.isoformat()}&to={DAY.isoformat()}", headers=hdr
    )
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


async def test_set_manual_override(client, db_session):
    school, _, child, _, hdr = await _setup(db_session)
    eid = await _enrollment_id(db_session, child.id)
    resp = await client.put(
        f"{STUDENTS}/{eid}/attendance", headers=hdr,
        json={"date": DAY.isoformat(), "status": "absent"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "absent" and data["marked_manually"] is True


async def test_attendance_tenant_isolation(client, db_session):
    school_a, _, child_a, _, _ = await _setup(db_session)
    _, _, _, _, hdr_b = await _setup(db_session)  # different school + admin
    await _engine(db_session).record_transition(child_a.id, school_a.id, "enter", ON_TIME)
    # Admin B's register for the same date sees only their own (empty) school.
    resp = await client.get(f"/api/v1/schools/attendance?date={DAY.isoformat()}", headers=hdr_b)
    assert all(r["child_id"] != str(child_a.id) for r in resp.json()["data"])


# --------------------------------------------------------------------------- #
# Reporting & export (Slice 3)
# --------------------------------------------------------------------------- #
REPORT = "/api/v1/schools/attendance/report"
EXPORT = "/api/v1/schools/attendance/export"
D1 = date(2026, 6, 15)   # Mon
D2 = date(2026, 6, 16)   # Tue
# DAY = 2026-06-17 (Wed)


async def _add_records(db, school_id, child_id, statuses, *, manually=False):
    """statuses: {date: status} → seed attendance_records directly."""
    for d, st in statuses.items():
        db.add(AttendanceRecord(
            school_id=school_id, child_id=child_id, date=d, status=st, marked_manually=manually,
        ))
    await db.flush()


async def _staff(db, school_id):
    staff = SchoolAdmin(
        school_id=school_id, email=f"st-{uuid.uuid4().hex[:8]}@s.test",
        password_hash=hash_secret("password123"), role="staff", active=True,
    )
    db.add(staff)
    await db.flush()
    hdr = {"Authorization": f"Bearer {create_access_token(str(staff.id), extra={'scope': 'school_admin'})}"}
    return staff, hdr


async def test_report_summary_and_rollup(client, db_session):
    school, _, child, _, hdr = await _setup(db_session)
    await _add_records(db_session, school.id, child.id, {D1: "on_time", D2: "absent", DAY: "late"})
    resp = await client.get(f"{REPORT}?from={D1.isoformat()}&to={DAY.isoformat()}", headers=hdr)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    s = data["summary"]
    assert s["records"] == 3 and s["students"] == 1
    assert s["by_status"]["on_time"] == 1
    assert s["by_status"]["late"] == 1
    assert s["by_status"]["absent"] == 1
    assert s["present_rate"] == round(2 / 3, 3)  # (on_time+late) / 3
    ps = data["per_student"][0]
    assert ps["child_name"] == "Aryan"
    assert ps["present_days"] == 2 and ps["total_days"] == 3
    assert ps["rate"] == round(2 / 3, 3)


async def test_report_class_grade_filter(client, db_session):
    school, _, child, _, hdr = await _setup(db_session)
    await _add_records(db_session, school.id, child.id, {D1: "on_time"})
    match = await client.get(
        f"{REPORT}?from={D1.isoformat()}&to={DAY.isoformat()}&class_grade=5A", headers=hdr
    )
    assert match.json()["data"]["summary"]["records"] == 1
    miss = await client.get(
        f"{REPORT}?from={D1.isoformat()}&to={DAY.isoformat()}&class_grade=9Z", headers=hdr
    )
    assert miss.json()["data"]["summary"]["records"] == 0
    assert miss.json()["data"]["per_student"] == []


async def test_report_staff_role_allowed(client, db_session):
    school, _, child, _, _ = await _setup(db_session)  # R4: staff may read reports
    _, staff_hdr = await _staff(db_session, school.id)
    await _add_records(db_session, school.id, child.id, {D1: "on_time"})
    resp = await client.get(f"{REPORT}?from={D1.isoformat()}&to={DAY.isoformat()}", headers=staff_hdr)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["summary"]["records"] == 1


async def test_report_invalid_range(client, db_session):
    school, _, _, _, hdr = await _setup(db_session)
    resp = await client.get(f"{REPORT}?from={DAY.isoformat()}&to={D1.isoformat()}", headers=hdr)
    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_RANGE"


async def test_report_range_too_large(client, db_session):
    school, _, _, _, hdr = await _setup(db_session)
    far = date(2028, 1, 1)  # > 366 days after D1
    resp = await client.get(f"{REPORT}?from={D1.isoformat()}&to={far.isoformat()}", headers=hdr)
    assert resp.status_code == 422
    assert resp.json()["code"] == "RANGE_TOO_LARGE"


async def test_report_tenant_isolation(client, db_session):
    school_a, _, child_a, _, _ = await _setup(db_session)
    _, _, _, _, hdr_b = await _setup(db_session)
    await _add_records(db_session, school_a.id, child_a.id, {D1: "on_time"})
    resp = await client.get(f"{REPORT}?from={D1.isoformat()}&to={DAY.isoformat()}", headers=hdr_b)
    assert resp.json()["data"]["summary"]["records"] == 0


async def test_export_csv(client, db_session):
    school, _, child, _, hdr = await _setup(db_session)
    await _add_records(db_session, school.id, child.id, {D1: "on_time", D2: "absent"})
    resp = await client.get(f"{EXPORT}?from={D1.isoformat()}&to={D2.isoformat()}", headers=hdr)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("date,child_id,child_name,class_grade,status")
    assert len(lines) == 3  # header + 2 records
    assert "Aryan" in resp.text
    assert "5A" in resp.text


async def test_export_empty_school_header_only(client, db_session):
    school, _, _, _, hdr = await _setup(db_session)
    resp = await client.get(f"{EXPORT}?from={D1.isoformat()}&to={D2.isoformat()}", headers=hdr)
    assert resp.status_code == 200
    assert len(resp.text.strip().splitlines()) == 1  # header only


async def test_export_invalid_range(client, db_session):
    school, _, _, _, hdr = await _setup(db_session)
    resp = await client.get(f"{EXPORT}?from={DAY.isoformat()}&to={D1.isoformat()}", headers=hdr)
    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_RANGE"
