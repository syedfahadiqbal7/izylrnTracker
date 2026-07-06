"""Aggregate v1 API router. Feature routers are included here as they land."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    audio,
    auth,
    bus,
    chat,
    children,
    driver,
    emergency,
    enrollments,
    family,
    geofences,
    i18n,
    routes,
    schools,
    share,
    sos,
    subscriptions,
    webhook,
)

api_router = APIRouter()
api_router.include_router(alerts.router)
api_router.include_router(audio.router)
api_router.include_router(auth.router)
api_router.include_router(bus.router)
api_router.include_router(chat.router)
api_router.include_router(children.router)
api_router.include_router(driver.router)
api_router.include_router(emergency.router)
api_router.include_router(enrollments.router)
api_router.include_router(family.router)
api_router.include_router(geofences.router)
api_router.include_router(i18n.router)
api_router.include_router(routes.router)
api_router.include_router(schools.router)
api_router.include_router(share.router)
api_router.include_router(sos.router)
api_router.include_router(subscriptions.router)
api_router.include_router(webhook.router)
