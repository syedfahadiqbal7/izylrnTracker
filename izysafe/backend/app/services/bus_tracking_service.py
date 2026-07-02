"""Bus live tracking (Sprint 8 Slice 5, F28).

The bus tracker rides the same Flow-A webhook as child devices; `LocationService`
caches its device-latest and flags `is_bus`, and the webhook schedules
`BusTrackingService.check_stops` off the hot path:

  * ``BusTrackingService`` (session_factory, redis, fcm) — on each bus position, for the
    active route(s) on that device, detect arrival within `bus_stop_radius_m` of a stop
    and fan a `bus_arrival` alert to the parents of children **assigned to that stop AND
    with bus_opt_in** (Decision B). A per-route+stop Redis debounce prevents re-alerting
    while the bus is parked.

  * ``BusLiveService`` (db, redis) — the parent-facing live read: the child's bus
    location (from the live cache) + their stop + a straight-line ETA, gated on the
    child's `bus_opt_in`.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_keys as rk
from app.core.config import settings
from app.core.errors import APIException
from app.core.geometry import haversine_m
from app.models.child import Child
from app.models.device import Device
from app.models.school import (
    BusAssignment,
    BusRoute,
    BusRouteStop,
    BusTrip,
    Driver,
    SchoolAdmin,
    StudentEnrollment,
)
from app.services.alert_service import AlertService
from app.services.children_service import ChildrenService
from app.services.fcm_gateway import FcmGateway

logger = logging.getLogger("izysafe.bus")


class BusTrackingService:
    def __init__(
        self, session_factory: Callable[[], AsyncSession], redis: Redis, fcm: FcmGateway
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.fcm = fcm

    async def check_stops(
        self, device_id: uuid.UUID, lat: float, lng: float, now: datetime | None = None
    ) -> None:
        now = now or datetime.now(timezone.utc)
        async with self.session_factory() as session:
            routes = (
                await session.execute(
                    select(BusRoute).where(
                        BusRoute.device_id == device_id, BusRoute.active.is_(True)
                    )
                )
            ).scalars().all()
            if not routes:
                return

            alerts = AlertService(session, self.fcm)
            fired = False
            for route in routes:
                stops = (
                    await session.execute(
                        select(BusRouteStop).where(BusRouteStop.route_id == route.id)
                    )
                ).scalars().all()
                for stop in stops:
                    if haversine_m(lat, lng, stop.lat, stop.lng) > settings.bus_stop_radius_m:
                        continue
                    if await self.redis.get(rk.bus_stop_debounce(route.id, stop.id)):
                        continue  # already announced this arrival recently
                    if await self._notify_stop(session, alerts, route, stop):
                        fired = True
                    await self.redis.set(
                        rk.bus_stop_debounce(route.id, stop.id), "1",
                        ex=settings.bus_stop_debounce_seconds,
                    )
            if fired:
                await session.commit()

    async def _notify_stop(self, session, alerts: AlertService, route: BusRoute, stop: BusRouteStop) -> bool:
        """Alert the bus-consented families of children boarding at this stop."""
        rows = (
            await session.execute(
                select(BusAssignment, Child)
                .join(Child, Child.id == BusAssignment.child_id)
                .join(
                    StudentEnrollment,
                    (StudentEnrollment.child_id == BusAssignment.child_id)
                    & (StudentEnrollment.school_id == route.school_id)
                    & (StudentEnrollment.bus_opt_in.is_(True)),
                )
                .where(BusAssignment.route_id == route.id, BusAssignment.stop_id == stop.id)
            )
        ).all()
        for _, child in rows:
            await alerts.notify_family(
                child.id, "bus_arrival",
                f"Bus arriving at {stop.name}",
                f"{child.name}'s bus is arriving at {stop.name}.",
                {"route_id": str(route.id), "stop_id": str(stop.id),
                 "route_name": route.name, "stop_name": stop.name},
            )
        if rows:
            logger.info("bus_arrival: route %s stop %s → %d family(ies)", route.id, stop.id, len(rows))
        return bool(rows)


class BusLiveService:
    """Parent-facing live bus location + ETA for one of their children."""

    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis
        self.children = ChildrenService(db)

    async def live_bus(self, user, child_id: uuid.UUID) -> dict:
        await self.children.get_child(user, child_id, require="view")  # 404 for non-members
        row = (
            await self.db.execute(
                select(BusAssignment, BusRoute)
                .join(BusRoute, BusRoute.id == BusAssignment.route_id)
                .join(
                    StudentEnrollment,
                    (StudentEnrollment.child_id == BusAssignment.child_id)
                    & (StudentEnrollment.school_id == BusRoute.school_id)
                    & (StudentEnrollment.bus_opt_in.is_(True)),
                )
                .where(BusAssignment.child_id == child_id)
            )
        ).first()
        if row is None:
            raise APIException(404, "NO_BUS", "No bus tracking available for this child")
        assignment, route = row

        location = None
        if route.device_id is not None:
            cached = await self.redis.get(rk.loc_device_latest(route.device_id))
            if cached:
                d = json.loads(cached)
                location = {"lat": d["lat"], "lng": d["lng"], "timestamp": d.get("ts")}

        stop = None
        if assignment.stop_id is not None:
            stop = (
                await self.db.execute(
                    select(BusRouteStop).where(BusRouteStop.id == assignment.stop_id)
                )
            ).scalar_one_or_none()

        eta = None
        if location and stop:
            km = haversine_m(location["lat"], location["lng"], stop.lat, stop.lng) / 1000
            eta = round(km / settings.bus_avg_speed_kmh * 60, 1)

        return {
            "route_id": route.id, "route_name": route.name, "location": location,
            "stop_id": stop.id if stop else None,
            "stop_name": stop.name if stop else None, "eta_minutes": eta,
        }

    async def fleet(self, admin: SchoolAdmin) -> list[dict]:
        """School-wide live view: every bus device with its cached position + online
        state, plus its route/driver/stops/roster-count and any active trip."""
        buses = (
            await self.db.execute(
                select(Device).where(
                    Device.school_id == admin.school_id,
                    Device.device_type == "bus",
                    Device.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        routes = (
            await self.db.execute(
                select(BusRoute).where(BusRoute.school_id == admin.school_id)
            )
        ).scalars().all()
        route_by_device = {r.device_id: r for r in routes if r.device_id is not None}
        route_ids = [r.id for r in routes]

        drivers: dict[uuid.UUID, Driver] = {}
        driver_ids = {r.driver_id for r in routes if r.driver_id is not None}
        if driver_ids:
            for d in (
                await self.db.execute(select(Driver).where(Driver.id.in_(driver_ids)))
            ).scalars().all():
                drivers[d.id] = d

        stops_by_route: dict[uuid.UUID, list[BusRouteStop]] = {}
        counts: dict[uuid.UUID, int] = {}
        trips: dict[uuid.UUID, BusTrip] = {}
        if route_ids:
            for s in (
                await self.db.execute(
                    select(BusRouteStop)
                    .where(BusRouteStop.route_id.in_(route_ids))
                    .order_by(BusRouteStop.seq)
                )
            ).scalars().all():
                stops_by_route.setdefault(s.route_id, []).append(s)
            for rid, cnt in (
                await self.db.execute(
                    select(BusAssignment.route_id, func.count())
                    .where(BusAssignment.route_id.in_(route_ids))
                    .group_by(BusAssignment.route_id)
                )
            ).all():
                counts[rid] = cnt
            for t in (
                await self.db.execute(
                    select(BusTrip).where(
                        BusTrip.route_id.in_(route_ids), BusTrip.status == "active"
                    )
                )
            ).scalars().all():
                trips[t.route_id] = t

        out: list[dict] = []
        for bus in buses:
            position = None
            cached = await self.redis.get(rk.loc_device_latest(bus.id))
            if cached:
                d = json.loads(cached)
                position = {"lat": d["lat"], "lng": d["lng"], "timestamp": d.get("ts")}
            online = (await self.redis.get(rk.device_online(bus.id))) is not None
            last_seen = None
            ls = await self.redis.get(rk.device_lastseen(bus.id))
            if ls:
                try:
                    last_seen = datetime.fromtimestamp(float(ls), tz=timezone.utc)
                except (ValueError, TypeError):
                    last_seen = None

            route = route_by_device.get(bus.id)
            route_out = driver_out = trip_out = None
            if route is not None:
                drv = drivers.get(route.driver_id) if route.driver_id else None
                if drv is not None:
                    driver_out = {"id": drv.id, "name": drv.name}
                route_out = {
                    "id": route.id, "name": route.name, "active": route.active,
                    "students": counts.get(route.id, 0),
                    "stops": [
                        {"id": s.id, "name": s.name, "lat": s.lat, "lng": s.lng, "seq": s.seq}
                        for s in stops_by_route.get(route.id, [])
                    ],
                }
                tr = trips.get(route.id)
                trip_out = {"active": tr is not None, "started_at": tr.started_at if tr else None}

            out.append({
                "bus_id": bus.id, "bus_name": bus.name, "imei": bus.imei,
                "traccar_id": bus.traccar_id, "online": online, "last_seen": last_seen,
                "position": position, "route": route_out, "driver": driver_out, "trip": trip_out,
            })
        return out
