"""Auth & billing: users, otp_sessions, subscriptions."""
from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UpdatedAtMixin, UUIDPkMixin


class User(Base, UUIDPkMixin, TimestampMixin, UpdatedAtMixin, SoftDeleteMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("language IN ('en','hi','ar')", name="ck_users_language"),
        CheckConstraint(
            "subscription_tier IN ('free','basic','premium','school')",
            name="ck_users_tier",
        ),
    )

    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    country_code: Mapped[str] = mapped_column(String(5), nullable=False, server_default="+91")
    name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255))
    photo_url: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10), nullable=False, server_default="en")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Kolkata")
    subscription_tier: Mapped[str] = mapped_column(String(20), nullable=False, server_default="free")
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fcm_token: Mapped[str | None] = mapped_column(Text)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quiet_hours_from: Mapped[time | None] = mapped_column(Time)
    quiet_hours_to: Mapped[time | None] = mapped_column(Time)

    # relationships
    family_links: Mapped[list["FamilyMember"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OtpSession(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "otp_sessions"
    __table_args__ = (
        CheckConstraint("channel IN ('whatsapp','sms')", name="ck_otp_channel"),
        Index("idx_otp_phone", "phone", "expires_at"),
    )

    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    channel: Mapped[str | None] = mapped_column(String(10), server_default="whatsapp")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Subscription(Base, UUIDPkMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("tier IN ('basic','premium','school')", name="ck_sub_tier"),
        CheckConstraint("gateway IN ('razorpay','stripe')", name="ck_sub_gateway"),
        CheckConstraint(
            "status IN ('active','past_due','cancelled','expired')", name="ck_sub_status"
        ),
        Index("idx_subscriptions_user", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    gateway: Mapped[str] = mapped_column(String(20), nullable=False)
    gateway_sub_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="active")
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(back_populates="subscriptions")
