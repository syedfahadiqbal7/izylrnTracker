"""Pydantic schemas for i18n (translations) + dynamic menus (Sprint 11, F23).

Localization is a wide table (one row per key, one column per locale) so the admin editor
edits a key across all languages at once. Menus are admin-managed navigation rows that the
Web Admin sidebar (and later the mobile nav) renders dynamically, restricted by role.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SUPPORTED_LOCALES = ("en", "hi", "ar")
Locale = Literal["en", "hi", "ar"]
AdminRole = Literal["admin", "staff"]
Platform = Literal["web", "mobile"]

# Right-to-left locales — the client flips layout direction for these.
RTL_LOCALES = frozenset({"ar"})

LOCALE_META: list[dict] = [
    {"code": "en", "name": "English", "native_name": "English", "rtl": False},
    {"code": "hi", "name": "Hindi", "native_name": "हिन्दी", "rtl": False},
    {"code": "ar", "name": "Arabic", "native_name": "العربية", "rtl": True},
]


# --------------------------------------------------------------------------- #
# Translations
# --------------------------------------------------------------------------- #
class TranslationResponse(BaseModel):
    """One key across every locale (localization editor row)."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    en: str
    hi: str | None = None
    ar: str | None = None
    updated_at: datetime


class TranslationUpsertRequest(BaseModel):
    """Create-or-update the values of a key. `en` is required (the fallback locale)."""

    en: str = Field(..., min_length=1, max_length=2000)
    hi: str | None = Field(None, max_length=2000)
    ar: str | None = Field(None, max_length=2000)


class TranslationCreateRequest(TranslationUpsertRequest):
    key: str = Field(..., min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9._-]+$")


# --------------------------------------------------------------------------- #
# Menu items
# --------------------------------------------------------------------------- #
class MenuItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_key: str
    label_key: str
    icon: str | None = None
    path: str
    platform: Platform
    sort_order: int
    visible: bool
    roles: list[str]


class MenuNavItem(BaseModel):
    """The slimmed shape the client renders (already role/visibility filtered)."""

    model_config = ConfigDict(from_attributes=True)

    item_key: str
    label_key: str
    icon: str | None = None
    path: str


class MenuItemCreateRequest(BaseModel):
    item_key: str = Field(..., min_length=1, max_length=60, pattern=r"^[a-z0-9_-]+$")
    label_key: str = Field(..., min_length=1, max_length=120)
    icon: str | None = Field(None, max_length=40)
    path: str = Field(..., min_length=1, max_length=120)
    platform: Platform = "web"
    sort_order: int = Field(0, ge=0, le=10000)
    visible: bool = True
    roles: list[AdminRole] = Field(default_factory=lambda: ["admin", "staff"])


class MenuItemUpdateRequest(BaseModel):
    label_key: str | None = Field(None, min_length=1, max_length=120)
    icon: str | None = Field(None, max_length=40)
    path: str | None = Field(None, min_length=1, max_length=120)
    sort_order: int | None = Field(None, ge=0, le=10000)
    visible: bool | None = None
    roles: list[AdminRole] | None = None


class MenuReorderRequest(BaseModel):
    """Ordered list of menu item ids — index → sort_order (atomic)."""

    ids: list[uuid.UUID] = Field(..., min_length=1)

    @field_validator("ids")
    @classmethod
    def _no_dupes(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(v)) != len(v):
            raise ValueError("duplicate ids")
        return v
