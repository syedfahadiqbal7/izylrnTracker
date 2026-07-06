"""Public i18n endpoints (Sprint 11, F23).

Unauthenticated on purpose: UI strings are not sensitive and the login screen needs them
before any token exists. Both the Web Admin Panel and the mobile app load a locale bundle
here at startup and whenever the user switches language. Admin management of the strings
lives under `/schools/localization` (role='admin').
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import APIException, success
from app.schemas.i18n import LOCALE_META, SUPPORTED_LOCALES
from app.services.i18n_service import I18nService

router = APIRouter(prefix="/i18n", tags=["i18n"])


@router.get("/locales")
async def list_locales() -> dict:
    """The supported languages (code, English + native name, RTL flag)."""
    return success(LOCALE_META)


@router.get("/{locale}")
async def get_bundle(
    locale: str = Path(..., min_length=2, max_length=5),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The full {key: value} translation bundle for one locale (English-fallback filled)."""
    if locale not in SUPPORTED_LOCALES:
        raise APIException(404, "UNKNOWN_LOCALE", f"Locale '{locale}' is not supported")
    strings = await I18nService(db).locale_map(locale)
    return success(strings, meta={"locale": locale, "count": len(strings)})
