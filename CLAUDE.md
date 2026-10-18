# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Orientation

This repo root (`C:\Fahad\IzylrnTracker`, git root) is a thin wrapper. **Almost all code, and the authoritative project context, live under `izysafe/`.**

- **[`izysafe/CLAUDE.md`](izysafe/CLAUDE.md) is the single source of truth** — locked architecture decisions, sprint state, invariants per subsystem (auth, geofences, SOS, payments, Celery, audio, i18n), Redis key reference, subscription-tier rules, and coding standards. Read it before doing anything substantive. If it conflicts with an older doc in `docs/`, that file wins.
  - Note: its §0 "Current State" lags the git history (it reports DB migration `0018` / Sprint 11 in flight, but migrations are now at `0020` and PRs #11–#13 are merged — Chat, polish, and dark-mode/i18n long-tail all landed). Trust git history + `backend/alembic/versions/` for exact current state; update §0 when you touch it.
- `docs/` (and `izysafe/docs/`) — product/spec sources: `IzySafe_Complete_Blueprint.md`, `IzySafe_User_Journey.docx` (deepest per-feature spec), the Sprint Plan, and user guides.

## Monorepo layout (`izysafe/`)

| Path | What | Stack |
|---|---|---|
| `backend/` | API, GPS pipeline, jobs | Python 3.12, FastAPI, SQLAlchemy **async** (asyncpg), Alembic (sync/psycopg2), Celery, Redis, Postgres 16, Traccar |
| `web-admin/` | School Admin web panel | React 18 + Vite 6 + TypeScript + Tailwind + shadcn/ui + TanStack Query + axios; Leaflet/OSM maps |
| `flutter/` | Parent mobile app (`izysafe_parent`) | Flutter 3, **Riverpod 2.6.1 (pinned — do not let `pub add` pull Riverpod 3)**, Dio + GoRouter + flutter_secure_storage, flutter_map/OSM |

`backend/app/` is layered: `api/` (routers) → `services/` (business logic) → `models/` + `schemas/` (SQLAlchemy / Pydantic v2), with `core/` (config, geometry, auth deps) and `worker/` (Celery app + beat + sync task wrappers).

## Commands

All commands run from `izysafe/` (not the repo root).

### Backend (run inside Docker; app/test code is volume-mounted so no rebuild needed unless deps change)
```bash
docker compose up -d                              # postgres, redis (6380→6379), traccar, backend@8000, celery-worker, celery-beat
docker compose exec -T backend pytest -q          # full suite (use `run --rm backend ...` if backend isn't up)
docker compose exec -T backend pytest -q tests/test_geofences.py            # one file
docker compose exec -T backend pytest -q tests/test_geofences.py::test_name # one test
docker compose exec -T backend ruff check app tests                         # lint (ruff; line-length 100, rules E/F/I/UP/B)
docker compose exec -T backend alembic upgrade head                         # apply migrations
```
Alembic runs **sync** via `settings.sync_database_url`; the app runs **async**. `pytest` config (asyncio auto-mode, testpaths) lives in `backend/pyproject.toml`.

**Verify a new migration against a fresh DB** (migration `0001` runs `db/schema.sql` verbatim, then later migrations ALTER on top — so every later migration must be idempotent):
```bash
# create a scratch DB and run `alembic upgrade head` against it with DATABASE_URL overridden
```

### Web admin (`web-admin/`)
```bash
npm install
npm run dev          # Vite dev server
npm run build        # tsc -b && vite build
npm run typecheck    # tsc -b --noEmit
npm run lint         # eslint
```

### Flutter parent app (`flutter/`)
```bash
flutter pub get
flutter analyze
flutter test
flutter run
```
CanvasKit web builds can't be driven by click-through automation (screenshot timeout, secure-storage = encrypted IndexedDB). Verify via `flutter analyze` / `flutter test` / `flutter build` + HTTP flow checks, not browser click-through.

## Working conventions (see `izysafe/CLAUDE.md` for the full set)

- **One feature per session, backend-first, tests alongside.** Never develop on `main`; use feature branches. Mock all external services (Traccar/FCM/Firebase/Redis/MSG91/Twilio/payment gateways) in tests — no live calls.
- **Uniform API envelope**: error `{error,code,message}`; success `{data}` or `{data,meta}`; everything under `/api/v1/`.
- **Never run geofence/speed/battery checks inline** in the request path — use FastAPI `BackgroundTasks`. Scheduled/heavy jobs go to Celery. The 5s batch location writer is a lifespan loop.
- Backend: always async, UUID PKs (except high-volume `locations`/`*_events` → BIGSERIAL), TIMESTAMPTZ in UTC, soft-delete filters (`deleted_at IS NULL`) by default.
- **Authorization flows through `family_members`** (children have no owner FK); non-members get **404**, not 403. Tier limits counted over the primary parent. Tier-gate with `require_tier(...)` → 402.
- Webhooks (`/webhook/*`) are secret-key authed, device endpoints use device tokens — **not** JWT; don't apply `get_current_user()` to them.
- Many external integrations are **graceful seams that no-op until creds are configured** (Firebase RTDB/FCM, Google Maps key, SMTP, payment checkout, Traccar/watch-hardware commands). Keep that pattern — pairing/alerts/etc. must still succeed locally when the dependency is unconfigured.
