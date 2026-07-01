"""Traccar webhooks (Flow A position forwarding).

Authenticated by the shared secret header, never JWT (CLAUDE.md §7). The handler
always returns 200 so Traccar's forward queue never backs up — unknown devices and
invalid fixes are acknowledged and dropped, not retried.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_battery_service,
    get_device_status_service,
    get_fcm_gateway,
    get_geofence_breach_service,
    get_chat_inbound_service,
    get_realtime_gateway,
    get_route_deviation_service,
    get_sos_alarm_service,
    get_speed_service,
    get_watch_removed_service,
    verify_traccar_secret,
)
from app.core.database import get_db
from app.core.errors import APIException
from app.core.redis import get_redis
from app.schemas.chat import WatchMessageIn
from app.schemas.location import TraccarForward
from app.services.battery_service import BatteryService
from app.services.chat_service import ChatInboundService
from app.services.device_status import DeviceStatusService
from app.services.fcm_gateway import FcmGateway
from app.services.geofence_breach_service import GeofenceBreachService
from app.services.location_service import LocationService, _coords_valid
from app.services.payment_service import SubscriptionWebhookService
from app.services.razorpay_gateway import RazorpayGateway
from app.services.realtime_gateway import RealtimeGateway
from app.services.route_deviation_service import RouteDeviationService
from app.services.sos_service import SosAlarmService
from app.services.speed_service import MIN_ALERT_SPEED_KMH, SpeedService
from app.services.stripe_gateway import StripeGateway
from app.services.watch_removed_service import WatchRemovedService

router = APIRouter(prefix="/webhook", tags=["webhook"])

# GT06 anti-tamper alarm strings (Decision D13 — validated on the hardware spike).
# Kept lowercase; the exact set may widen once we see real device payloads.
_REMOVAL_ALARMS = {"tamper", "removing", "remove", "removed"}
_WORN_ALARMS = {"tamperend", "worn", "wear", "wearing"}


def _classify_alarm(alarm: str) -> str:
    """Map a lowercased Traccar alarm string to a handler: sos | removed | worn | other.
    An empty alarm on this endpoint is treated as SOS (the historical contract)."""
    if alarm in ("", "sos"):
        return "sos"
    if alarm in _REMOVAL_ALARMS:
        return "removed"
    if alarm in _WORN_ALARMS:
        return "worn"
    return "other"


@router.post("/traccar", dependencies=[Depends(verify_traccar_secret)])
async def traccar_position(
    body: TraccarForward,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    realtime: RealtimeGateway = Depends(get_realtime_gateway),
    device_status: DeviceStatusService = Depends(get_device_status_service),
    battery: BatteryService = Depends(get_battery_service),
    speed: SpeedService = Depends(get_speed_service),
    geofence: GeofenceBreachService = Depends(get_geofence_breach_service),
    route: RouteDeviationService = Depends(get_route_deviation_service),
) -> dict:
    """Ingest one decoded position: cache it, mark the device online, buffer it for
    the batch writer (hot path). Off the hot path in BackgroundTasks: the Firebase
    live-map write, the device online-transition reconcile, and the battery + speed
    checks. Returns 200 with the disposition (accepted / ignored)."""
    result = await LocationService(db, redis).process_update(body)
    if not result.stored:
        return {"status": "ignored", "reason": result.reason}

    background.add_task(
        realtime.update_live_location, str(result.child_id), result.live_payload
    )
    background.add_task(device_status.reconcile_online, result.device_id)
    # Geofence breach detection — skipped on stale fixes (an old position must not
    # raise a fresh enter/exit alert; CLAUDE.md §5).
    if not result.stale:
        background.add_task(
            geofence.check_all_fences,
            result.child_id, result.lat, result.lng, result.device_id, result.speed,
        )
        # Safe Route deviation — same off-hot-path, stale-skipped treatment as fences.
        background.add_task(
            route.check_all_routes,
            result.child_id, result.lat, result.lng, result.device_id,
        )
    if result.battery is not None:
        background.add_task(battery.evaluate, result.device_id, result.battery)
    # Only when fast enough to possibly exceed a threshold — skips the DB read for
    # the overwhelmingly common slow/stationary pings.
    if result.speed is not None and result.speed > MIN_ALERT_SPEED_KMH:
        background.add_task(speed.evaluate, result.child_id, result.speed)
    return {"status": "accepted", "stale": result.stale}


@router.post("/traccar/alarm", dependencies=[Depends(verify_traccar_secret)])
async def traccar_alarm(
    body: TraccarForward,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    sos: SosAlarmService = Depends(get_sos_alarm_service),
    watch: WatchRemovedService = Depends(get_watch_removed_service),
) -> dict:
    """Ingest a GT06 alarm. Secret-header authed like the position webhook; always 200
    so Traccar's queue can't back up. The alarm string routes it: SOS (Flow C) triggers
    the emergency fan-out; a tamper/removal alarm starts a watch-removed episode (F18);
    a re-wear alarm clears it; anything else is ignored. All handlers run off the hot
    path in a BackgroundTask. SOS coordinates fall back to the last-known fix when the
    alarm lacks a valid one (the service flags it approximate)."""
    pos = body.position
    kind = _classify_alarm((pos.attributes.alarm or "").lower())
    if kind == "other":
        return {"status": "ignored", "reason": "not_sos_alarm"}

    unique_id = body.device.unique_id if body.device else None
    resolved = await LocationService(db, redis).resolve_device(pos.device_id, unique_id)
    if resolved is None:
        return {"status": "ignored", "reason": "unknown_device"}
    device_id, child_id = resolved

    if kind == "removed":
        background.add_task(watch.mark_removed, device_id, child_id)
        return {"status": "accepted", "kind": "watch_removed"}
    if kind == "worn":
        background.add_task(watch.mark_worn, device_id)
        return {"status": "accepted", "kind": "watch_worn"}

    lat = lng = None
    if pos.valid and _coords_valid(pos.latitude, pos.longitude):
        lat, lng = pos.latitude, pos.longitude

    background.add_task(sos.trigger_from_alarm, child_id, device_id, lat, lng, pos.address)
    return {"status": "accepted", "kind": "sos"}


@router.post("/traccar/message", dependencies=[Depends(verify_traccar_secret)])
async def traccar_message(
    body: WatchMessageIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    chat: ChatInboundService = Depends(get_chat_inbound_service),
) -> dict:
    """Ingest an inbound watch→parent chat message (F23). Secret-header authed like the
    other Traccar webhooks; always 200. Resolution is inline; the store + `chat_reply`
    fan-out runs off the hot path in a BackgroundTask. NB: the watch→backend transport
    is GT06-model-specific and pending the hardware spike (Decision D17)."""
    resolved = await LocationService(db, redis).resolve_device(body.device_id, body.unique_id)
    if resolved is None:
        return {"status": "ignored", "reason": "unknown_device"}
    device_id, child_id = resolved

    background.add_task(chat.receive, device_id, child_id, body.content)
    return {"status": "accepted", "kind": "chat"}


@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> dict:
    """Razorpay subscription webhook (Sprint 6). HMAC-SHA256 verified against the raw
    body (never JWT); an invalid signature is 401. On a verified event the subscription
    state is applied inline — idempotent per `X-Razorpay-Event-Id`. A genuine DB error
    propagates (5xx) so Razorpay retries and no activation is lost."""
    body = await request.body()
    if not RazorpayGateway.verify_webhook(body, request.headers.get("X-Razorpay-Signature")):
        raise APIException(401, "WEBHOOK_UNAUTHORIZED", "Invalid webhook signature")

    payload = json.loads(body)
    entity = (payload.get("payload") or {}).get("subscription", {}).get("entity") or {}
    disposition = await SubscriptionWebhookService(db, redis, fcm).apply_razorpay(
        payload.get("event", ""), request.headers.get("X-Razorpay-Event-Id"), entity
    )
    return {"status": "ok", "disposition": disposition}


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    fcm: FcmGateway = Depends(get_fcm_gateway),
) -> dict:
    """Stripe subscription webhook (Sprint 6). Verifies the `Stripe-Signature` HMAC over
    the raw body (401 on failure); applies the event inline, idempotent per Stripe event
    id. A genuine DB error propagates (5xx) so Stripe retries and no activation is lost."""
    body = await request.body()
    if not StripeGateway.verify_webhook(body, request.headers.get("Stripe-Signature")):
        raise APIException(401, "WEBHOOK_UNAUTHORIZED", "Invalid webhook signature")

    payload = json.loads(body)
    entity = (payload.get("data") or {}).get("object") or {}
    disposition = await SubscriptionWebhookService(db, redis, fcm).apply_stripe(
        payload.get("type", ""), payload.get("id"), entity
    )
    return {"status": "ok", "disposition": disposition}
