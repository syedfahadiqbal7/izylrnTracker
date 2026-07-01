"""Subscription endpoints (Sprint 6 Slice 1): plan catalog + current state.

Read-only this slice. Checkout (`POST /subscriptions/checkout`) and the gateway webhooks
that activate/renew subscriptions arrive in Slices 2 (Razorpay) and 3 (Stripe).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.errors import success
from app.models.user import User
from app.schemas.subscription import PlanResponse, SubscriptionMeResponse
from app.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("/plans")
async def list_plans(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The plan catalog priced in the user's currency (INR for India, AED for the UAE)."""
    currency, rows = SubscriptionService(db).list_plans(current_user)
    plans = [PlanResponse(**r).model_dump(mode="json") for r in rows]
    return success(plans, meta={"currency": currency})


@router.get("/me")
async def get_my_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The user's current subscription: effective tier, status, and period end."""
    state = await SubscriptionService(db).get_current(current_user)
    return success(SubscriptionMeResponse(**state).model_dump(mode="json"))
