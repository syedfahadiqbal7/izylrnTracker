"""Aggregate v1 API router. Feature routers are included here as they land."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import alerts, auth, children, emergency, family, geofences, sos, webhook

api_router = APIRouter()
api_router.include_router(alerts.router)
api_router.include_router(auth.router)
api_router.include_router(children.router)
api_router.include_router(emergency.router)
api_router.include_router(family.router)
api_router.include_router(geofences.router)
api_router.include_router(sos.router)
api_router.include_router(webhook.router)
