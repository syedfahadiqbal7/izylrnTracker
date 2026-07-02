"""Tests for driver trip actions (Sprint 10 Slice 1b).

Trip start/end (ownership, one-per-driver), manual arrived (bus_arrival to boarding
families + debounce + stop-on-route guard), manual pickup (bus_boarded + boarding row +
dedup + on-route guard), and the active_trip flag in today's-routes.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.security import create_access_token, hash_secret
from app.models.alert import Alert
from app.models.child import Child, FamilyMember
from app.models.school import (
    BusAssignment, BusBoarding, BusRoute, BusRouteStop, Driver, School, StudentEnrollment,
)
from app.models.user import User

DRIVER = "/api/v1/drivers"


async def _setup(db, *, bus_opt_in=True, assign=True):
    school = School(name="Green Valley", timezone="UTC")
    db.add(school)
    await db.flush()
    driver = Driver(school_id=school.id, name="Ravi", phone="+9198" + f"{uuid.uuid4().int % 10**8:08d}",
                    password_hash=hash_secret("drivercode1"), active=True)
    db.add(driver)
    await db.flush()
    route = BusRoute(school_id=school.id, name="R1", driver_id=driver.id, active=True)
    db.add(route)
    await db.flush()
    stop = BusRouteStop(route_id=route.id, name="Main Gate", lat=18.5, lng=73.8, seq=1)
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
    dhdr = {"Authorization": f"Bearer {create_access_token(str(driver.id), extra={'scope': 'driver'})}"}
    return school, driver, route, stop, child, dhdr


async def _alerts(db, child_id, atype):
    return (await db.execute(
        select(func.count()).select_from(Alert).where(Alert.child_id == child_id, Alert.type == atype)
    )).scalar_one()


async def _start(client, dhdr, route_id):
    return await client.post(f"{DRIVER}/me/trip/start", headers=dhdr, json={"route_id": str(route_id)})


# --------------------------------------------------------------------------- #
# Trip start / end
# --------------------------------------------------------------------------- #
async def test_start_trip(client, db_session):
    _, _, route, _, _, dhdr = await _setup(db_session)
    resp = await _start(client, dhdr, route.id)
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["status"] == "active"
    assert resp.json()["data"]["route_id"] == str(route.id)


async def test_start_foreign_route_404(client, db_session):
    _, _, _, _, _, dhdr = await _setup(db_session)
    resp = await _start(client, dhdr, uuid.uuid4())
    assert resp.status_code == 404
    assert resp.json()["code"] == "ROUTE_NOT_FOUND"


async def test_start_twice_conflict(client, db_session):
    _, _, route, _, _, dhdr = await _setup(db_session)
    assert (await _start(client, dhdr, route.id)).status_code == 201
    resp = await _start(client, dhdr, route.id)
    assert resp.status_code == 409
    assert resp.json()["code"] == "TRIP_IN_PROGRESS"


async def test_end_trip(client, db_session):
    _, _, route, _, _, dhdr = await _setup(db_session)
    await _start(client, dhdr, route.id)
    resp = await client.post(f"{DRIVER}/me/trip/end", headers=dhdr)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ended"
    assert resp.json()["data"]["ended_at"] is not None


async def test_end_no_active_trip(client, db_session):
    _, _, _, _, _, dhdr = await _setup(db_session)
    resp = await client.post(f"{DRIVER}/me/trip/end", headers=dhdr)
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_ACTIVE_TRIP"


async def test_end_then_restart_ok(client, db_session):
    _, _, route, _, _, dhdr = await _setup(db_session)
    await _start(client, dhdr, route.id)
    await client.post(f"{DRIVER}/me/trip/end", headers=dhdr)
    assert (await _start(client, dhdr, route.id)).status_code == 201  # a fresh trip


async def test_routes_show_active_trip(client, db_session):
    _, _, route, _, _, dhdr = await _setup(db_session)
    await _start(client, dhdr, route.id)
    data = (await client.get(f"{DRIVER}/me/routes", headers=dhdr)).json()["data"]
    assert data[0]["active_trip"] is not None
    assert "trip_id" in data[0]["active_trip"]


# --------------------------------------------------------------------------- #
# Arrived
# --------------------------------------------------------------------------- #
async def test_arrived_notifies_families(client, db_session, fake_fcm_gateway):
    _, _, route, stop, child, dhdr = await _setup(db_session)
    await _start(client, dhdr, route.id)
    resp = await client.post(f"{DRIVER}/me/stop/{stop.id}/arrived", headers=dhdr)
    assert resp.status_code == 200
    assert resp.json()["data"]["notified"] == 1
    assert await _alerts(db_session, child.id, "bus_arrival") == 1
    assert fake_fcm_gateway.calls[-1]["data"]["type"] == "bus_arrival"


async def test_arrived_debounced(client, db_session):
    _, _, route, stop, child, dhdr = await _setup(db_session)
    await _start(client, dhdr, route.id)
    await client.post(f"{DRIVER}/me/stop/{stop.id}/arrived", headers=dhdr)
    second = await client.post(f"{DRIVER}/me/stop/{stop.id}/arrived", headers=dhdr)
    assert second.json()["data"]["notified"] == 0  # debounced
    assert await _alerts(db_session, child.id, "bus_arrival") == 1


async def test_arrived_stop_not_on_route(client, db_session):
    _, _, route, _, _, dhdr = await _setup(db_session)
    await _start(client, dhdr, route.id)
    resp = await client.post(f"{DRIVER}/me/stop/{uuid.uuid4()}/arrived", headers=dhdr)
    assert resp.status_code == 400
    assert resp.json()["code"] == "STOP_NOT_ON_ROUTE"


async def test_arrived_no_active_trip(client, db_session):
    _, _, _, stop, _, dhdr = await _setup(db_session)
    resp = await client.post(f"{DRIVER}/me/stop/{stop.id}/arrived", headers=dhdr)
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_ACTIVE_TRIP"


# --------------------------------------------------------------------------- #
# Picked up
# --------------------------------------------------------------------------- #
async def test_picked_up_records_and_notifies(client, db_session, fake_fcm_gateway):
    _, _, route, stop, child, dhdr = await _setup(db_session)
    await _start(client, dhdr, route.id)
    resp = await client.post(f"{DRIVER}/me/child/{child.id}/picked-up", headers=dhdr)
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["child_id"] == str(child.id)
    assert resp.json()["data"]["stop_id"] == str(stop.id)  # defaults to assigned stop
    assert await _alerts(db_session, child.id, "bus_boarded") == 1
    boardings = (await db_session.execute(select(func.count()).select_from(BusBoarding))).scalar_one()
    assert boardings == 1


async def test_picked_up_duplicate(client, db_session):
    _, _, route, _, child, dhdr = await _setup(db_session)
    await _start(client, dhdr, route.id)
    assert (await client.post(f"{DRIVER}/me/child/{child.id}/picked-up", headers=dhdr)).status_code == 201
    resp = await client.post(f"{DRIVER}/me/child/{child.id}/picked-up", headers=dhdr)
    assert resp.status_code == 409
    assert resp.json()["code"] == "ALREADY_BOARDED"


async def test_picked_up_child_not_on_route(client, db_session):
    _, _, route, _, _, dhdr = await _setup(db_session, assign=False)  # child not assigned
    await _start(client, dhdr, route.id)
    _, _, _, _, other_child, _ = await _setup(db_session)  # unrelated child
    resp = await client.post(f"{DRIVER}/me/child/{other_child.id}/picked-up", headers=dhdr)
    assert resp.status_code == 404
    assert resp.json()["code"] == "CHILD_NOT_ON_ROUTE"


async def test_picked_up_no_active_trip(client, db_session):
    _, _, _, _, child, dhdr = await _setup(db_session)
    resp = await client.post(f"{DRIVER}/me/child/{child.id}/picked-up", headers=dhdr)
    assert resp.status_code == 404
    assert resp.json()["code"] == "NO_ACTIVE_TRIP"
