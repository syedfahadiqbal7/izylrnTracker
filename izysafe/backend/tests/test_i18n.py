"""Tests for the i18n foundation (Sprint 11, F23): public locale bundles + admin-managed
translations and dynamic menus.

The seeded translations/menu_items (migration 0012) are committed rows visible to every
test; tests assert against/around that seed and clean up via the per-test rollback.
"""
from __future__ import annotations

import uuid

from app.core.security import create_access_token, hash_secret
from app.models.school import School, SchoolAdmin

LOCALES = "/api/v1/i18n/locales"
MENU = "/api/v1/schools/menu"
LOCALIZATION = "/api/v1/schools/localization"
MENU_ITEMS = "/api/v1/schools/menu-items"


async def _admin(db, *, role="admin"):
    school = School(name="Green Valley", timezone="UTC")
    db.add(school)
    await db.flush()
    admin = SchoolAdmin(
        school_id=school.id, email=f"a-{uuid.uuid4().hex[:8]}@s.test",
        password_hash=hash_secret("password1"), name="Head", role=role, active=True,
    )
    db.add(admin)
    await db.flush()
    hdr = {"Authorization": f"Bearer {create_access_token(str(admin.id), extra={'scope': 'school_admin'})}"}
    return admin, hdr


# --------------------------------------------------------------------------- #
# Public locale bundles (no auth)
# --------------------------------------------------------------------------- #
async def test_list_locales(client):
    resp = await client.get(LOCALES)
    assert resp.status_code == 200
    codes = [l["code"] for l in resp.json()["data"]]
    assert codes == ["en", "hi", "ar"]
    ar = next(l for l in resp.json()["data"] if l["code"] == "ar")
    assert ar["rtl"] is True


async def test_get_bundle_returns_keyed_strings(client):
    resp = await client.get("/api/v1/i18n/en")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["nav.dashboard"] == "Dashboard"
    assert resp.json()["meta"]["locale"] == "en"


async def test_bundle_falls_back_to_english(client, db_session):
    # A key with no Hindi value should surface the English value in the hi bundle.
    _, hdr = await _admin(db_session)
    await client.post(
        LOCALIZATION, headers=hdr,
        json={"key": "test.fallback", "en": "OnlyEnglish", "hi": None, "ar": None},
    )
    data = (await client.get("/api/v1/i18n/hi")).json()["data"]
    assert data["test.fallback"] == "OnlyEnglish"


async def test_get_bundle_unknown_locale_404(client):
    resp = await client.get("/api/v1/i18n/zz")
    assert resp.status_code == 404
    assert resp.json()["code"] == "UNKNOWN_LOCALE"


# --------------------------------------------------------------------------- #
# Dynamic menu (role-filtered) — drives the sidebar
# --------------------------------------------------------------------------- #
async def test_menu_admin_sees_admin_only_items(client, db_session):
    _, hdr = await _admin(db_session, role="admin")
    keys = [m["item_key"] for m in (await client.get(MENU, headers=hdr)).json()["data"]]
    assert "audit" in keys and "menus" in keys and "dashboard" in keys


async def test_menu_staff_excludes_admin_only_items(client, db_session):
    _, hdr = await _admin(db_session, role="staff")
    keys = [m["item_key"] for m in (await client.get(MENU, headers=hdr)).json()["data"]]
    assert "dashboard" in keys
    assert "audit" not in keys and "menus" not in keys


async def test_menu_requires_auth(client):
    assert (await client.get(MENU)).status_code == 401


# --------------------------------------------------------------------------- #
# Localization management (admin only)
# --------------------------------------------------------------------------- #
async def test_list_translations_requires_admin(client, db_session):
    _, staff = await _admin(db_session, role="staff")
    assert (await client.get(LOCALIZATION, headers=staff)).status_code == 403


async def test_create_and_update_translation_roundtrip(client, db_session):
    _, hdr = await _admin(db_session)
    key = f"test.greeting_{uuid.uuid4().hex[:6]}"
    created = await client.post(
        LOCALIZATION, headers=hdr, json={"key": key, "en": "Hi", "hi": "नमस्ते", "ar": "مرحبا"}
    )
    assert created.status_code == 201, created.text
    # Edit it, then confirm the new value is served in the ar bundle.
    upd = await client.put(f"{LOCALIZATION}/{key}", headers=hdr, json={"en": "Hello", "ar": "أهلا"})
    assert upd.status_code == 200
    assert upd.json()["data"]["en"] == "Hello"
    assert (await client.get("/api/v1/i18n/ar")).json()["data"][key] == "أهلا"


async def test_delete_translation(client, db_session):
    _, hdr = await _admin(db_session)
    key = f"test.tmp_{uuid.uuid4().hex[:6]}"
    await client.post(LOCALIZATION, headers=hdr, json={"key": key, "en": "X"})
    assert (await client.delete(f"{LOCALIZATION}/{key}", headers=hdr)).status_code == 200
    assert (await client.delete(f"{LOCALIZATION}/{key}", headers=hdr)).status_code == 404


async def test_create_translation_rejects_bad_key(client, db_session):
    _, hdr = await _admin(db_session)
    resp = await client.post(LOCALIZATION, headers=hdr, json={"key": "bad key!", "en": "X"})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Menu management (admin only)
# --------------------------------------------------------------------------- #
async def test_menu_item_crud(client, db_session):
    _, hdr = await _admin(db_session)
    key = f"custom_{uuid.uuid4().hex[:6]}"
    created = await client.post(
        MENU_ITEMS, headers=hdr,
        json={"item_key": key, "label_key": "nav.custom", "icon": "Star",
              "path": "/custom", "roles": ["admin"], "sort_order": 5},
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["data"]["id"]
    # Hide it → it drops out of the rendered menu.
    upd = await client.patch(f"{MENU_ITEMS}/{item_id}", headers=hdr, json={"visible": False})
    assert upd.status_code == 200 and upd.json()["data"]["visible"] is False
    render_keys = [m["item_key"] for m in (await client.get(MENU, headers=hdr)).json()["data"]]
    assert key not in render_keys
    # But it's still in the management list.
    mgmt_keys = [m["item_key"] for m in (await client.get(MENU_ITEMS, headers=hdr)).json()["data"]]
    assert key in mgmt_keys
    # Delete.
    assert (await client.delete(f"{MENU_ITEMS}/{item_id}", headers=hdr)).status_code == 200


async def test_menu_item_duplicate_key_409(client, db_session):
    _, hdr = await _admin(db_session)
    resp = await client.post(
        MENU_ITEMS, headers=hdr,
        json={"item_key": "dashboard", "label_key": "nav.dashboard", "path": "/"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "DUPLICATE_KEY"


async def test_menu_reorder(client, db_session):
    _, hdr = await _admin(db_session)
    items = (await client.get(MENU_ITEMS, headers=hdr)).json()["data"]
    ids = [m["id"] for m in items]
    reversed_ids = list(reversed(ids))
    resp = await client.put(f"{MENU_ITEMS}/reorder", headers=hdr, json={"ids": reversed_ids})
    assert resp.status_code == 200, resp.text
    new_order = [m["id"] for m in resp.json()["data"]]
    assert new_order == reversed_ids


async def test_menu_management_rejects_staff(client, db_session):
    _, staff = await _admin(db_session, role="staff")
    assert (await client.get(MENU_ITEMS, headers=staff)).status_code == 403
    assert (
        await client.post(MENU_ITEMS, headers=staff, json={"item_key": "x", "label_key": "y", "path": "/x"})
    ).status_code == 403
