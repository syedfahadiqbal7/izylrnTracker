"""i18n + dynamic-menu service (Sprint 11, F23).

Owns the two admin-managed foundations behind multi-lingual support:
  * translations — the wide (key + en/hi/ar) localization table. `locale_map` serves a
    single-locale bundle (falling back to English for any untranslated value) to both the
    Web Admin Panel and the mobile app; the rest are the admin CRUD used by the editor.
  * menu_items — dynamic navigation. `nav_for` returns the visible, role-permitted items
    for the caller (drives the sidebar); the rest are the admin CRUD (create / update /
    reorder / show-hide / delete).

Translations and menus are app-wide config (not school-scoped); management is gated to
role='admin' at the endpoint layer.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import APIException
from app.models.integration import MenuItem, Translation
from app.schemas.i18n import SUPPORTED_LOCALES


class I18nService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Translations
    # ------------------------------------------------------------------ #
    async def locale_map(self, locale: str) -> dict[str, str]:
        """{key: value} for one locale — the runtime bundle the frontends load.

        Any value missing in the requested locale falls back to English so the UI never
        shows a raw key. English requests return the `en` column directly.
        """
        rows = (await self.db.execute(select(Translation))).scalars().all()
        out: dict[str, str] = {}
        for r in rows:
            value = getattr(r, locale, None) if locale in SUPPORTED_LOCALES else None
            out[r.key] = value if value not in (None, "") else r.en
        return out

    async def list_translations(self) -> list[Translation]:
        return list(
            (await self.db.execute(select(Translation).order_by(Translation.key)))
            .scalars()
            .all()
        )

    async def upsert_translation(
        self, key: str, en: str, hi: str | None, ar: str | None
    ) -> Translation:
        """Create the key or overwrite its values (idempotent editor save)."""
        stmt = (
            pg_insert(Translation)
            .values(key=key, en=en, hi=hi, ar=ar)
            .on_conflict_do_update(
                index_elements=[Translation.key],
                set_={"en": en, "hi": hi, "ar": ar, "updated_at": func.now()},
            )
            .returning(Translation)
        )
        row = (await self.db.execute(stmt)).scalar_one()
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def delete_translation(self, key: str) -> None:
        row = await self.db.get(Translation, key)
        if row is None:
            raise APIException(404, "NOT_FOUND", "Translation key not found")
        await self.db.delete(row)
        await self.db.commit()

    # ------------------------------------------------------------------ #
    # Menus
    # ------------------------------------------------------------------ #
    async def nav_for(self, role: str, platform: str = "web") -> list[MenuItem]:
        """Visible items the given role may see, ordered — drives the sidebar."""
        rows = (
            await self.db.execute(
                select(MenuItem)
                .where(MenuItem.platform == platform, MenuItem.visible.is_(True))
                .order_by(MenuItem.sort_order, MenuItem.item_key)
            )
        ).scalars().all()
        return [m for m in rows if not m.roles or role in m.roles]

    async def list_menu(self, platform: str = "web") -> list[MenuItem]:
        """Every item (incl. hidden) for the management table."""
        return list(
            (
                await self.db.execute(
                    select(MenuItem)
                    .where(MenuItem.platform == platform)
                    .order_by(MenuItem.sort_order, MenuItem.item_key)
                )
            ).scalars().all()
        )

    async def create_menu(self, data: dict) -> MenuItem:
        exists = (
            await self.db.execute(
                select(MenuItem.id).where(MenuItem.item_key == data["item_key"])
            )
        ).scalar_one_or_none()
        if exists is not None:
            raise APIException(409, "DUPLICATE_KEY", "A menu item with that key already exists")
        item = MenuItem(**data)
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def update_menu(self, item_id: uuid.UUID, data: dict) -> MenuItem:
        item = await self.db.get(MenuItem, item_id)
        if item is None:
            raise APIException(404, "NOT_FOUND", "Menu item not found")
        for k, v in data.items():
            setattr(item, k, v)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete_menu(self, item_id: uuid.UUID) -> None:
        item = await self.db.get(MenuItem, item_id)
        if item is None:
            raise APIException(404, "NOT_FOUND", "Menu item not found")
        await self.db.delete(item)
        await self.db.commit()

    async def reorder_menu(self, ids: list[uuid.UUID]) -> list[MenuItem]:
        """Set sort_order from the given order. Every id must exist (all-or-nothing)."""
        existing = set(
            (await self.db.execute(select(MenuItem.id))).scalars().all()
        )
        missing = [str(i) for i in ids if i not in existing]
        if missing:
            raise APIException(404, "NOT_FOUND", "Unknown menu item id(s) in reorder")
        for order, item_id in enumerate(ids, start=1):
            await self.db.execute(
                update(MenuItem).where(MenuItem.id == item_id).values(sort_order=order * 10)
            )
        await self.db.commit()
        return await self.list_menu()


def func_now():
    from sqlalchemy import func

    return func.now()
