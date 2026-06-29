"""Children & family: children, family_members, invites.

Ownership note (CLAUDE.md §3.10): children has NO owner FK. Authorization is
expressed entirely through family_members; the creator is inserted as
role='parent', is_primary=True, can_manage=True.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UpdatedAtMixin, UUIDPkMixin

_ROLE_CHECK = "role IN ('parent','guardian','grandparent','teacher','relative')"


class Child(Base, UUIDPkMixin, TimestampMixin, UpdatedAtMixin, SoftDeleteMixin):
    __tablename__ = "children"
    __table_args__ = (
        CheckConstraint(
            "speed_threshold_kmh IN (20,30,40,60,80,100,120)", name="ck_child_speed"
        ),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(50))
    dob: Mapped[date | None] = mapped_column(Date)
    photo_url: Mapped[str | None] = mapped_column(Text)
    school_name: Mapped[str | None] = mapped_column(String(200))
    class_grade: Mapped[str | None] = mapped_column(String(50))
    # School Mode (F16)
    school_mode_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    school_hours_from: Mapped[time | None] = mapped_column(Time)
    school_hours_to: Mapped[time | None] = mapped_column(Time)
    school_active_days: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("ARRAY[1,2,3,4,5]")
    )
    # Speed Alert (F15)
    speed_alert_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    speed_threshold_kmh: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    # Teen Mode (F30)
    teen_mode_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    devices: Mapped[list["Device"]] = relationship(  # noqa: F821
        back_populates="child", cascade="all, delete-orphan"
    )
    family_members: Mapped[list["FamilyMember"]] = relationship(
        back_populates="child", cascade="all, delete-orphan"
    )
    geofences: Mapped[list["Geofence"]] = relationship(  # noqa: F821
        back_populates="child", cascade="all, delete-orphan"
    )


class FamilyMember(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "family_members"
    __table_args__ = (
        CheckConstraint(_ROLE_CHECK, name="ck_family_role"),
        UniqueConstraint("child_id", "user_id", name="uq_family_child_user"),
        Index("idx_family_user", "user_id"),
        Index("idx_family_child", "child_id"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="guardian")
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    can_call: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    can_manage: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    child: Mapped["Child"] = relationship(back_populates="family_members")
    user: Mapped["User"] = relationship(back_populates="family_links")  # noqa: F821


class Invite(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint(_ROLE_CHECK, name="ck_invite_role"),
        Index("idx_invites_token", "token"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="guardian")
    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    can_call: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    can_manage: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
