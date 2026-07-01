"""Subscription endpoints (Sprint 6 Slice 1): plan catalog + current state.

Read-only this slice. Checkout (`POST /subscriptions/checkout`) and the gateway webhooks
that activate/renew subscriptions arrive in Slices 2 (Razorpay) and 3 (Stripe).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_razorpay_gateway
from app.core.database import get_db
from app.core.errors import success
from app.models.user import User
from app.schemas.subscription import (
    CheckoutRequest,
    CheckoutResponse,
    PlanResponse,
    SubscriptionMeResponse,
)
from app.services.payment_service import PaymentService
from app.services.razorpay_gateway import RazorpayGateway
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


@router.post("/checkout", status_code=201)
async def create_checkout(
    payload: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    razorpay: RazorpayGateway = Depends(get_razorpay_gateway),
) -> dict:
    """Start a recurring subscription for the target tier and return the params the app
    needs to open the gateway's checkout. The tier is granted only when the gateway
    webhook confirms payment (never client-reported)."""
    result = await PaymentService(db, razorpay).create_checkout(current_user, payload.tier)
    return success(CheckoutResponse(**result).model_dump(mode="json"))


@router.get("/me")
async def get_my_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The user's current subscription: effective tier, status, and period end."""
    state = await SubscriptionService(db).get_current(current_user)
    return success(SubscriptionMeResponse(**state).model_dump(mode="json"))
