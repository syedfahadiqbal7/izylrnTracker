"""Tests for bus live tracking (Sprint 8 Slice 5, F28).

Covers bus-device registration (school-owned, child-less), the stop-arrival engine
(radius + bus_opt_in + stop-specific recipients + debounce), the parent live-bus read
(location + ETA, opt-in gated), and the webhook bus-position branch (device-cache only,
no child cache; arrival → bus_arrival alert).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import func, select

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.security import create_access_token, hash_secret
from app.models.alert import Alert
from app.models.child import Child, FamilyMember
from app.models.device import Device
from app.models.school import BusAssignment, BusRoute, BusRouteStop, School, SchoolAdmin, StudentEnrollment
from app.models.user import User
from app.services.bus_tracking_service import BusLiveService, BusTrackingService
from tests.conftest import NonClosingSession
from tests.fakes import FakeFcmGateway

SECRET_HEADERS = {"X-Traccar-Secret": settings.traccar_webhook_secret}
BUSES = "/api/v1/schools/buses"
CLAT, CLNG = 18.5204, 73.8567
AT_STOP = (18.5204, 73.8567)
FAR = (19.0, 74.0)


async def _admin(db, name="Green Valley"):
    school = School(name=name, timezone="UTC")
    db.add(school)
    await db.flush()
    admin = SchoolAdmin(school_id=school.id, email=f"a-{uuid.uuid4().hex[:8]}@s.test",
                        password_hash=hash_secret("password123"), role="admin", active=True)
    db.add(admin)
    await db.flush()
    hdr = {"Authorization": f"Bearer {create_access_token(str(admin.id), extra={'scope': 'school_admin'})}"}
    return school, admin, hdr


async def _full_setup(db, *, bus_opt_in=True, assign=True, active_route=True, traccar_id=None):
    school, admin, hdr = await _admin(db)
    bus = Device(school_id=school.id, child_id=None, name="Bus 1", device_type="bus",
                 imei=uuid.uuid4().hex[:15], traccar_id=traccar_id)
    db.add(bus)
    await db.flush()
    route = BusRoute(school_id=school.id, name="R1", device_id=bus.id, active=active_route)
    db.add(route)
    await db.flush()
    stop = BusRouteStop(route_id=route.id, name="Main Gate", lat=CLAT, lng=CLNG, seq=1)
    db.add(stop)
    parent = User(phone="+9198" + f"{uuid.uuid4().int % 10**8:08d}", country_code="+91", fcm_token="ptok")
    db.add(parent)
    await db.flush()
    child = Child(name="Aryan")
    db.add(child)
    await db.flush()
    db.add(FamilyMember(child_id=child.id, user_id=parent.id, role="parent",
                        is_primary=True, can_view=True, can_call=True, can_manage=True))
    db.add(StudentEnrollment(school_id=school.id, child_id=child.id, parent_opt_in=True, bus_opt_in=bus_opt_in))
    if assign:
        db.add(BusAssignment(route_id=route.id, child_id=child.id, stop_id=stop.id))
    await db.flush()
    parent_hdr = {"Authorization": f"Bearer {create_access_token(str(parent.id))}"}
    return dict(school=school, hdr=hdr, bus=bus, route=route, stop=stop, child=child, parent_hdr=parent_hdr)


def _engine(db, redis, fcm=None):
    return BusTrackingService(lambda: NonClosingSession(db), redis, fcm or FakeFcmGateway())


async def _bus_alerts(db, child_id):
    return (await db.execute(
        select(func.count()).select_from(Alert).where(Alert.child_id == child_id, Alert.type == "bus_arrival")
    )).scalar_one()


# --------------------------------------------------------------------------- #
# Bus device registration
# --------------------------------------------------------------------------- #
async def test_register_bus(client, db_session):
    school, _, hdr = await _admin(db_session)
    resp = await client.post(BUSES, headers=hdr, json={"name": "Bus 1", "imei": "999000111222", "traccar_id": 555})
    assert resp.status_code == 201, resp.text
    dev = (await db_session.execute(select(Device).where(Device.id == uuid.UUID(resp.json()["data"]["id"])))).scalar_one()
    assert dev.device_type == "bus" and dev.child_id is None and dev.school_id == school.id


async def test_register_bus_duplicate_imei(client, db_session):
    _, _, hdr = await _admin(db_session)
    body = {"name": "Bus", "imei": "999000111333"}
    assert (await client.post(BUSES, headers=hdr, json=body)).status_code == 201
    resp = await client.post(BUSES, headers=hdr, json=body)
    assert resp.status_code == 409 and resp.json()["code"] == "IMEI_TAKEN"


async def test_list_and_delete_bus(client, db_session):
    _, _, hdr = await _admin(db_session)
    bid = (await client.post(BUSES, headers=hdr, json={"name": "Bus", "imei": "999000111444"})).json()["data"]["id"]
    assert len((await client.get(BUSES, headers=hdr)).json()["data"]) == 1
    assert (await client.delete(f"{BUSES}/{bid}", headers=hdr)).status_code == 200
    assert len((await client.get(BUSES, headers=hdr)).json()["data"]) == 0


# --------------------------------------------------------------------------- #
# Stop-arrival engine
# --------------------------------------------------------------------------- #
async def test_arrival_alerts_assigned_optin(db_session, redis_client):
    s = await _full_setup(db_session)
    fcm = FakeFcmGateway()
    await _engine(db_session, redis_client, fcm).check_stops(s["bus"].id, *AT_STOP)
    assert await _bus_alerts(db_session, s["child"].id) == 1
    assert fcm.calls[-1]["data"]["type"] == "bus_arrival"
    assert await redis_client.get(rk.bus_stop_debounce(s["route"].id, s["stop"].id)) == "1"


async def test_no_alert_when_far(db_session, redis_client):
    s = await _full_setup(db_session)
    await _engine(db_session, redis_client).check_stops(s["bus"].id, *FAR)
    assert await _bus_alerts(db_session, s["child"].id) == 0


async def test_arrival_debounced(db_session, redis_client):
    s = await _full_setup(db_session)
    eng = _engine(db_session, redis_client)
    await eng.check_stops(s["bus"].id, *AT_STOP)
    await eng.check_stops(s["bus"].id, *AT_STOP)  # still parked → debounced
    assert await _bus_alerts(db_session, s["child"].id) == 1


async def test_no_alert_without_bus_optin(db_session, redis_client):
    s = await _full_setup(db_session, bus_opt_in=False)
    await _engine(db_session, redis_client).check_stops(s["bus"].id, *AT_STOP)
    assert await _bus_alerts(db_session, s["child"].id) == 0


async def test_only_stop_recipients_alerted(db_session, redis_client):
    # Child assigned to stop A; bus arrives at a different stop B → child not alerted.
    s = await _full_setup(db_session)
    stop_b = BusRouteStop(route_id=s["route"].id, name="Far Stop", lat=19.0, lng=74.0, seq=2)
    db_session.add(stop_b)
    await db_session.flush()
    await _engine(db_session, redis_client).check_stops(s["bus"].id, 19.0, 74.0)  # at stop B
    assert await _bus_alerts(db_session, s["child"].id) == 0  # child boards at A


# --------------------------------------------------------------------------- #
# Parent live-bus read
# --------------------------------------------------------------------------- #
async def test_live_bus(client, db_session, redis_client):
    s = await _full_setup(db_session)
    await redis_client.set(rk.loc_device_latest(s["bus"].id),
                           json.dumps({"lat": 18.60, "lng": 73.90, "ts": "2026-06-17T09:00:00+00:00"}))
    resp = await client.get(f"/api/v1/children/{s['child'].id}/bus", headers=s["parent_hdr"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["route_name"] == "R1"
    assert data["location"]["lat"] == 18.60
    assert data["stop_name"] == "Main Gate"
    assert data["eta_minutes"] is not None and data["eta_minutes"] > 0


async def test_live_bus_no_optin_404(client, db_session, redis_client):
    s = await _full_setup(db_session, bus_opt_in=False)
    resp = await client.get(f"/api/v1/children/{s['child'].id}/bus", headers=s["parent_hdr"])
    assert resp.status_code == 404 and resp.json()["code"] == "NO_BUS"


async def test_live_bus_non_member_404(client, db_session, auth_headers):
    s = await _full_setup(db_session)
    resp = await client.get(f"/api/v1/children/{s['child'].id}/bus", headers=auth_headers)
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# School fleet live view (map)
# --------------------------------------------------------------------------- #
async def test_fleet_live(client, db_session, redis_client):
    s = await _full_setup(db_session)
    await redis_client.set(rk.loc_device_latest(s["bus"].id),
                           json.dumps({"lat": 18.60, "lng": 73.90, "ts": "2026-06-17T09:00:00+00:00"}))
    await redis_client.set(rk.device_online(s["bus"].id), "1")
    resp = await client.get("/api/v1/schools/buses/live", headers=s["hdr"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    b = data[0]
    assert b["online"] is True
    assert b["position"]["lat"] == 18.60
    assert b["route"]["name"] == "R1"
    assert b["route"]["students"] == 1
    assert len(b["route"]["stops"]) == 1
    assert b["route"]["stops"][0]["name"] == "Main Gate"


async def test_fleet_offline_no_position(client, db_session, redis_client):
    s = await _full_setup(db_session)  # no redis keys set → offline, no fix
    b = (await client.get("/api/v1/schools/buses/live", headers=s["hdr"])).json()["data"][0]
    assert b["online"] is False and b["position"] is None


async def test_fleet_tenant_isolation(client, db_session):
    s = await _full_setup(db_session)
    _, _, hdr_b = await _admin(db_session, name="Other School")
    assert (await client.get("/api/v1/schools/buses/live", headers=hdr_b)).json()["data"] == []


# --------------------------------------------------------------------------- #
# Live child tracking (kid trackers)
# --------------------------------------------------------------------------- #
async def _kid_setup(db, *, parent_opt_in=True, location_opt_in=True, all_hours=True):
    school = School(
        name="Green Valley", timezone="UTC",
        school_days=[1, 2, 3, 4, 5, 6, 7] if all_hours else [1, 2, 3, 4, 5],
        arrival_window_from=time(0, 0) if all_hours else time(7, 0),
        day_ends_at=time(23, 59) if all_hours else time(16, 0),
    )
    db.add(school)
    await db.flush()
    admin = SchoolAdmin(school_id=school.id, email=f"a-{uuid.uuid4().hex[:8]}@s.test",
                        password_hash=hash_secret("password123"), role="admin", active=True)
    db.add(admin)
    parent = User(phone="+9198" + f"{uuid.uuid4().int % 10**8:08d}", country_code="+91")
    db.add(parent)
    await db.flush()
    child = Child(name="Aryan")
    db.add(child)
    await db.flush()
    db.add(FamilyMember(child_id=child.id, user_id=parent.id, role="parent",
                        is_primary=True, can_view=True, can_call=True, can_manage=True))
    db.add(StudentEnrollment(school_id=school.id, child_id=child.id,
                             parent_opt_in=parent_opt_in, location_opt_in=location_opt_in))
    db.add(Device(child_id=child.id, name="Aryan's Watch", device_type="watch",
                  imei=uuid.uuid4().hex[:15], is_online=True, last_battery=88))
    await db.flush()
    hdr = {"Authorization": f"Bearer {create_access_token(str(admin.id), extra={'scope': 'school_admin'})}"}
    return dict(school=school, admin=admin, hdr=hdr, child=child)


async def test_children_live_consented(client, db_session, redis_client):
    s = await _kid_setup(db_session)
    await redis_client.set(rk.loc_child_latest(s["child"].id),
                           json.dumps({"lat": 18.52, "lng": 73.85, "ts": "2026-07-03T05:00:00+00:00", "battery": 88}))
    resp = await client.get("/api/v1/schools/children/live", headers=s["hdr"])
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    c = data[0]
    assert c["child_name"] == "Aryan" and c["in_window"] is True
    assert c["position"]["lat"] == 18.52 and c["battery"] == 88
    assert c["device_name"] == "Aryan's Watch" and c["online"] is True


async def test_children_live_requires_location_consent(client, db_session, redis_client):
    s = await _kid_setup(db_session, location_opt_in=False)
    await redis_client.set(rk.loc_child_latest(s["child"].id), json.dumps({"lat": 18.5, "lng": 73.8}))
    assert (await client.get("/api/v1/schools/children/live", headers=s["hdr"])).json()["data"] == []


async def test_children_live_requires_parent_optin(client, db_session, redis_client):
    s = await _kid_setup(db_session, parent_opt_in=False)
    assert (await client.get("/api/v1/schools/children/live", headers=s["hdr"])).json()["data"] == []


async def test_children_live_position_hidden_outside_hours(db_session, redis_client):
    # Mon–Fri 07:00–16:00 school; query Wed 20:00 UTC → listed but no live position.
    s = await _kid_setup(db_session, all_hours=False)
    await redis_client.set(rk.loc_child_latest(s["child"].id), json.dumps({"lat": 18.5, "lng": 73.8}))
    out = await BusLiveService(db_session, redis_client).children_fleet(
        s["admin"], now=datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc)
    )
    assert len(out) == 1 and out[0]["in_window"] is False and out[0]["position"] is None


async def test_children_live_position_shown_in_hours(db_session, redis_client):
    s = await _kid_setup(db_session, all_hours=False)
    await redis_client.set(rk.loc_child_latest(s["child"].id), json.dumps({"lat": 18.5, "lng": 73.8}))
    out = await BusLiveService(db_session, redis_client).children_fleet(
        s["admin"], now=datetime(2026, 6, 17, 9, 0, tzinfo=timezone.utc)  # Wed 09:00 → in window
    )
    assert out[0]["in_window"] is True and out[0]["position"]["lat"] == 18.5


async def test_children_live_tenant_isolation(client, db_session, redis_client):
    s = await _kid_setup(db_session)
    _, _, hdr_b = await _admin(db_session, name="Other School")
    assert (await client.get("/api/v1/schools/children/live", headers=hdr_b)).json()["data"] == []


# --------------------------------------------------------------------------- #
# Webhook bus-position branch
# --------------------------------------------------------------------------- #
def _pos(traccar_id, imei, lat, lng):
    return {"position": {"deviceId": traccar_id, "latitude": lat, "longitude": lng,
                         "valid": True, "attributes": {}},
            "device": {"id": traccar_id, "uniqueId": imei}}


async def test_webhook_bus_position_cached_not_as_child(client, db_session, redis_client):
    s = await _full_setup(db_session, traccar_id=8801)
    resp = await client.post("/api/v1/webhook/traccar", headers=SECRET_HEADERS,
                             json=_pos(8801, s["bus"].imei, 18.55, 73.88))
    assert resp.json()["kind"] == "bus"
    assert await redis_client.get(rk.loc_device_latest(s["bus"].id)) is not None
    # A bus has no child → the child-latest cache must NOT be written under the child.
    assert await redis_client.get(rk.loc_child_latest(s["child"].id)) is None


async def test_webhook_bus_arrival_fires(client, db_session, redis_client, fake_fcm_gateway):
    s = await _full_setup(db_session, traccar_id=8802)
    resp = await client.post("/api/v1/webhook/traccar", headers=SECRET_HEADERS,
                             json=_pos(8802, s["bus"].imei, *AT_STOP))
    assert resp.json()["kind"] == "bus"
    # The stop-arrival BackgroundTask fans out a bus_arrival to the assigned family.
    assert await _bus_alerts(db_session, s["child"].id) == 1
