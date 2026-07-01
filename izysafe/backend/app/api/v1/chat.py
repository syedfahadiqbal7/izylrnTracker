"""Chat endpoints (Sprint 7 Slice 6, F23).

Send + history nest under a child. Sending is Basic+ (gated in the service). Delivery
to the watch is a best-effort Traccar SIM command whose end-to-end behaviour is pending
the hardware spike (Decision D17); the inbound (watch→parent) direction arrives on the
secret-authed message webhook.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_traccar_gateway
from app.core.database import get_db
from app.core.errors import success
from app.core.redis import get_redis
from app.models.comms import ChatMessage
from app.models.user import User
from app.schemas.chat import ChatMessageResponse, ChatSendRequest
from app.services.chat_service import ChatService
from app.services.traccar_gateway import TraccarGateway

router = APIRouter(tags=["chat"])


def _serialize(message: ChatMessage) -> dict:
    return ChatMessageResponse.model_validate(message).model_dump(mode="json")


@router.post("/children/{child_id}/chat", status_code=201)
async def send_chat(
    child_id: uuid.UUID,
    payload: ChatSendRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    traccar: TraccarGateway = Depends(get_traccar_gateway),
) -> dict:
    """Send a text to the child's watch (requires membership + Basic+)."""
    message = await ChatService(db, redis, traccar).send(
        current_user, child_id, payload.content
    )
    return success(_serialize(message))


@router.get("/children/{child_id}/chat")
async def list_chat(
    child_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    traccar: TraccarGateway = Depends(get_traccar_gateway),
) -> dict:
    """Chat history for a child (most recent first)."""
    rows, total = await ChatService(db, redis, traccar).list(
        current_user, child_id, limit, offset
    )
    return success(
        [_serialize(m) for m in rows],
        meta={"total": total, "limit": limit, "offset": offset},
    )
