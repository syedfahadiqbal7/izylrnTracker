"""Safe Route CRUD endpoints (Sprint 7 Slice 1, F20).

Routes follow the geofence contract: create/list nest under a child
(`/children/{child_id}/routes`); detail/update/delete address a route directly
(`/routes/{route_id}`). Safe Routes is Premium — the tier gate lives in the service
(→ 402 SAFE_ROUTES_REQUIRES_PREMIUM). Deviation alerts are driven off the position
webhook by `RouteDeviationService`; there is no per-route event-history endpoint
(deviations are recorded in the alert inbox, not a ledger table).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import success
from app.core.redis import get_redis
from app.models.route import SafeRoute
from app.models.user import User
from app.schemas.route import SafeRouteCreate, SafeRouteResponse, SafeRouteUpdate
from app.services.route_service import RouteService

router = APIRouter(tags=["routes"])


def _serialize(route: SafeRoute) -> dict:
    return SafeRouteResponse.model_validate(route).model_dump(mode="json")


@router.post("/children/{child_id}/routes", status_code=201)
async def create_route(
    child_id: uuid.UUID,
    payload: SafeRouteCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Create a safe route for a child (requires manage permission + Premium tier)."""
    route = await RouteService(db, redis).create_route(
        current_user, child_id, payload.model_dump(exclude_unset=True)
    )
    return success(_serialize(route))


@router.get("/children/{child_id}/routes")
async def list_routes(
    child_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """List all safe routes for a child."""
    rows = await RouteService(db, redis).list_routes(current_user, child_id)
    return success([_serialize(r) for r in rows])


@router.get("/routes/{route_id}")
async def get_route(
    route_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    route = await RouteService(db, redis).get_route(current_user, route_id, "view")
    return success(_serialize(route))


@router.put("/routes/{route_id}")
async def update_route(
    route_id: uuid.UUID,
    payload: SafeRouteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Update a safe route (requires manage permission)."""
    route = await RouteService(db, redis).update_route(
        current_user, route_id, payload.model_dump(exclude_unset=True)
    )
    return success(_serialize(route))


@router.delete("/routes/{route_id}")
async def delete_route(
    route_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> dict:
    """Delete a safe route (requires manage permission)."""
    await RouteService(db, redis).delete_route(current_user, route_id)
    return success({"success": True})
