# IzySafe — Project Context for Claude

> Single source of truth for AI-assisted development. Read this first, every session,
> alongside the detailed specs in `../docs/`. If anything here conflicts with an older
> file in `docs/`, **this file wins** — it encodes the Sprint-0 resolutions.

---

## 0. Current State (update each sprint; keep terse)

- **Done & on `main`:** Sprint 0 (infra, 33-table schema, partitioning) + Sprint 1 (Auth, User, Children, Family — 29 endpoints, 88 tests). PR #1 merged.
- **In progress:** Sprint 2 (branch `sprint-2-location`) — real-time location pipeline. **Slice 1 DONE:** `POST /api/v1/webhook/traccar` hot path (secret-header auth → device resolve w/ Redis cache → validate → Redis latest cache + online TTL + `batch:locations` buffer). **Slice 2 DONE:** `BatchWriter` lifespan task (5s loop, RPOP-count drain ≤1000, bulk insert → `locations`, transient-fail re-queue, poison-row drop, `finally` shutdown flush). **Slice 3 DONE:** `RealtimeGateway` (Firebase RT DB `live_locations/{child_id}/latest`, sync SDK wrapped in `asyncio.to_thread`, no-op when creds absent) written off the hot path via `BackgroundTasks`; `firebase-admin>=6.5` added (image rebuild); **live-verified against real `izysafe-dev` RTDB**. **Slice 4 DONE:** device online/offline — `DeviceStatusService.reconcile_online` (webhook BackgroundTask, `device:{id}:status` marker) + `DeviceStatusMonitor` lifespan sweep (60s, offline after 15min, `device_offline` alert); shared `FcmGateway` + `AlertService.notify_family`. **Slice 5 DONE:** battery alerts — `BatteryService.evaluate` (webhook BackgroundTask) reads device fresh, persists `last_battery` only on change, fires `low_battery` (≤`battery_threshold`) / `critical_battery` (≤5%) with per-level 4h debounce (`battery_alerted:{device_id}`), low→critical escalation, recharge reset; `AlertService.notify_user` added; Sprint-1 guardian-accepted FCM cleared (accept endpoint → `family_join` to inviter). 136 tests. Remaining: 6 speed · 7 GET latest + geofence stub.
- **Run:** `cd izysafe && docker compose up -d` (postgres, redis@6380→6379, traccar, backend@8000). Tests: `docker compose run --rm backend pytest -q`.
- **Auth runtime invariants:** JWT HS256 + Redis denylist (`denylist:{access,refresh}:{jti}`) + refresh rotation. `get_current_user` is **fail-open** on Redis down; refresh/logout **fail-closed**. Webhooks/device endpoints are NOT JWT (secret-key / device token).
- **Authorization invariant:** all child access flows through `family_members` (no owner FK). Non-members get **404** (not 403). Primary parent is protected (can't be removed/demoted). Tier limits counted over the **primary parent**, incl. pending invites.
- **Validation pattern:** structural/enum → Pydantic (422 `VALIDATION_ERROR`); semantic/business → service raises `APIException` with a precise code (e.g. `INVALID_PHONE`, `CHILD_LIMIT_REACHED`).
- **Test isolation:** module-level async engine uses **NullPool** (function-scoped loops); per-test session bound to one connection with `join_transaction_mode="create_savepoint"` + outer rollback; fakeredis + fake gateways via `dependency_overrides`.
- **Deferred (by design):** 30-day soft-delete purge job → Sprint 6 (Celery). (Guardian-accepted FCM done in Sprint 2 Slice 5.)
- **Gotchas:** Alembic runs **sync** (psycopg2) via `settings.sync_database_url`; app is async (asyncpg). `zoneinfo` needs the `tzdata` dep (slim image). Traccar XML comments must not contain `--`. Image rebuild only needed when deps change; app/test code is volume-mounted.

---

## 1. Project Context

**What:** GPS child-safety platform for **India + UAE**. Sold standalone and bundled with
affordable 4G GPS kids' watches. Privacy-first, ad-free, no data selling.

**Why it wins (USP):** native GPS-watch support, multiple devices per child (watch +
bag tracker + phone), Hindi/Arabic UI, India/UAE-localized pricing, future IzyLrn (EdTech)
integration, and a school tier (web dashboard, attendance, bus tracking) scaling to 10,000+ students.

**Scope:** 35 features across 3 phases, built **one feature at a time, backend-first, with tests**,
over 11 sprints (S0–S10, ~17 weeks). Stakeholder: **Faraz**. Repo: `farooquifaraz/izysafe`.

**Canonical reference docs (in `../docs/`):**
- `IzySafe_Complete_Blueprint.md` — product/architecture master
- `IzySafe_Development_Sprint_Plan.docx` — the build plan we follow (S0–S10)
- `IzySafe_User_Journey.docx` — per-feature validations, exceptions, edge cases (deepest spec)
- Canonical DB schema: `backend/db/schema.sql` (33 tables)

---

## 2. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Mobile | Flutter 3, Riverpod 2, Dio + Retrofit, GoRouter, google_maps_flutter | Clean architecture, null-safe |
| Backend | Python 3.12, FastAPI, SQLAlchemy **async**, Alembic | snake_case, type hints, Pydantic v2 |
| Database | PostgreSQL 16 | `locations` partitioned monthly by `timestamp` |
| Cache | Redis 7 | live location, geofence state, rate limiting, online status |
| Real-time | Firebase Realtime DB | live map streams (parent app listens) |
| Push | FCM | high-priority FCM bypasses DND for SOS |
| GPS middleware | Traccar (open-source) | GT06 :5023, TK103 :5002, H02 :5013; **PostgreSQL backend (never H2)** |
| Auth | JWT (HS256) + OTP via WhatsApp/SMS | access 24h, refresh 30d |
| Web admin | React 18, TypeScript, Vite, TailwindCSS + shadcn/ui, TanStack Query | Sprint 9+ |
| Payments | Razorpay (India) + Stripe (UAE) | Sprint 6 |
| OTP delivery | MSG91 (WhatsApp primary) + Twilio (SMS fallback) | 30s WhatsApp→SMS failover |
| Storage | Cloudflare R2 | child photos, weekly PDFs |
| Maps/geocode | Google Maps API | maps, directions, reverse geocoding |
| Infra | Docker Compose (dev) → Hostinger VPS (prod) | Firebase **Blaze** plan required |

---

## 3. Locked Architecture Decisions (Sprint 0 resolutions)

These are **final**. Do not re-litigate them when generating code.

1. **lat/lng = `DOUBLE PRECISION`** everywhere (not DECIMAL). Float math on the hot path; PostGIS-ready.
2. **User columns:** `subscription_tier`, `subscription_expires_at`, `country_code` (default `'+91'`). (Sprint DDL names, not Blueprint's `sub_tier`/`sub_expires`.)
3. **`locations` keeps** `accuracy, speed, altitude, bearing, address` (nullable) **+ denormalized `child_id`** (NOT NULL) so per-child history avoids a join.
4. **Geofence schedule = discrete columns** `active_days INTEGER[] / active_from / active_to` (not JSONB). `zone_type` (home/school/tuition/grandparents/sports/other) — School Mode keys off `zone_type='school'`; Multiple Safe Addresses reuses the same table (no separate table).
5. **Partitioning:** `create_locations_partition(year, month)` fn + bootstrap from current month +18 + a `DEFAULT` catch-all partition. A monthly Celery-beat cron rolls the window forward. **Never hardcode year partitions.**
6. **One active SOS per child** enforced by a partial unique index `WHERE status='active'`.
7. **JWT = HS256.** Access token 24h, refresh 30d, stored in Flutter Secure Storage.
8. **Pairing code TTL = 30 min** (configurable via `expires_at`).
9. **OTP:** 6-digit, bcrypt-hashed, 10-min expiry, max 3 verify attempts. Rate limit 5/phone/hr + 20/IP/hr (Redis). 30s WhatsApp→SMS fallback.
10. **Ownership model:** `children` has **no owner FK**. Ownership/authorization is expressed entirely via `family_members`. The creator is inserted as `role='parent', is_primary=TRUE, can_manage=TRUE`. Supports two-primary-parents + guardian sharing. Tier "max children" counted over children where the user is the primary parent.
11. **SOS auth:** the real trigger is the **Traccar alarm webhook** `/webhook/traccar/alarm` (secret-key/HMAC). `POST /sos/trigger` exists only as an **internal device-token** endpoint for app/phone-originated SOS. JWT is NOT used for the device trigger.
12. **Audio (Sound Around F11 / Two-way Call F12):** use **Traccar SIM commands** — GT06 `MONITOR` (watch silently calls parent = sound around) and `CALLBACK` (two-way call over the watch's own SIM). **No media server / WebRTC.** Validate on real hardware before building (Sprint 0 spike).
13. **Sound Around mic:** ships in **both IN + UAE** at launch, gated by an explicit **consent screen + always-on watch mic indicator + `audio_sessions` audit log**. (UAE legal sign-off handled in parallel by the business.)
14. **Firebase dev:** a real Firebase **dev project (Blaze)** — no emulator in docker-compose.
15. **Timeline:** follow the **Sprint Plan (S0–S10)**. The older "22 weeks" figures are superseded.

---

## 4. Background-Task Strategy (decisive rule)

Pick the mechanism by job type — do not mix arbitrarily:

| Job type | Mechanism | Examples |
|---|---|---|
| In-request, per-location-update checks | **FastAPI `BackgroundTasks`** (in-process, no broker) | geofence check, speed check, battery check, watch-removed check |
| Single long-lived loop | **FastAPI lifespan task** | the 5-second batch location writer (Redis list → bulk PG insert) |
| Scheduled / heavy / cross-cutting | **Celery + Redis broker** (added Sprint 6) | weekly PDF report (F25), daily subscription-expiry sweep, monthly partition roll-forward, nightly ML retrain (F33) |

**Rule:** never run geofence/speed checks inline in the API response path — always `BackgroundTasks`.

---

## 5. Critical Data Flows

### Flow A — Live location (target < 1 second)
```
Watch → GT06 packet → Traccar (:5023)
  → POST /api/v1/webhook/traccar  (static X-Traccar-Secret header, constant-time compare)
    → location_service.process_update():
        validate (lat/lng bounds, ts fresh ≤5min, accuracy)
        Redis SETEX  location:child:{id}:latest      TTL 24h   (instant)
        Redis SETEX  location:device:{id}:latest     TTL 24h
        Redis SETEX  device:{id}:online = 1          TTL 300s  (sliding)
        Firebase RT DB  live_locations/{child_id}/latest        (parent streams this)
        Redis LPUSH  batch:locations                  (flushed every 5s → PostgreSQL)
        BackgroundTask: geofence_service.check_all_fences(child_id, lat, lng)
  → Parent Flutter Firebase listener → Google Maps marker animates
```

### Flow B — Geofence breach → FCM
```
check_all_fences():
  circle: haversine(); polygon: ray-casting point-in-polygon
  honor schedule (active_days / active_from / active_to) — suppress FCM outside window
  prev state ← Redis geofence:{child}:{fence}:inside
  on transition (enter/exit):
     INSERT geofence_events + INSERT alerts (one per family member)
     fcm_service.send_to_family(child_id, title, body)
     SETEX geofence:{child}:{fence}:inside = new_state  TTL 72h
  5-minute debounce (geofence_debounce:{child}:{fence}) prevents jitter spam
```

### Flow C — SOS (highest priority, always overrides School Mode)
```
Watch SOS button held 3s → GT06 alarm → Traccar
  → POST /api/v1/webhook/traccar/alarm  (secret key)
    → dedup (ignore if active SOS for child within 30s)
      INSERT sos_events (one-active-per-child enforced by partial unique index)
      Firebase RT DB  sos/{child_id} = {active:true, lat, lng, triggered_at}
      fcm_service.send_urgent() to ALL family + emergency_contacts (android priority MAX, bypass DND)
  → Parent app: FULL-SCREEN modal (not swipe-dismissible) until someone taps Resolve
  → Resolve clears sos/{child_id}.active for everyone simultaneously
```

---

## 6. Coding Standards

### Python (backend)
- `snake_case`; **type hints everywhere**; **Pydantic v2** schemas.
- SQLAlchemy **async** (`AsyncSession`); never block the event loop.
- All DB IDs are **UUID** (except high-volume append tables `locations`/`*_events` → BIGSERIAL).
- All timestamps **TIMESTAMPTZ stored in UTC**; convert to user timezone for display only.
- Soft delete (`deleted_at`) on `users`, `children`, `devices`. Always filter `deleted_at IS NULL` in default queries.
- Auth dependency: `get_current_user()` on every endpoint except `/auth/*` and `/webhook/*`.
- Subscription gating: `require_tier("basic"|"premium")` dependency → returns **402** with upgrade message.

### Dart (Flutter)
- `camelCase`; **null safety**; no `dynamic`.
- Riverpod: `FutureProvider` (one-shot fetch), `StreamProvider` (Firebase live), `StateNotifierProvider` (forms/flows).
- All API via the shared Dio client (`core/api/dio_client.dart`) with JWT interceptor + refresh-retry.
- Handle **401 → redirect to login**, **402 → open subscription screen**.
- Navigation via GoRouter (`context.push` / `context.go`); deep-link support for notification taps.

### API contract (uniform)
- **Error:** `{ "error": true, "code": "ERROR_CODE", "message": "Human-readable" }`
- **Success (single):** `{ "data": { ... } }`
- **Success (list):** `{ "data": [ ... ], "meta": { "page": N, "total": M } }`
- Versioned under `/api/v1/`. Base URL (prod): `https://api.izysafe.com/v1`.

---

## 7. Auth Rules

- OTP via WhatsApp (primary) → SMS fallback after 30s. 6 digits, bcrypt hash, 10-min expiry, ≤3 attempts.
- JWT **HS256**; access 24h, refresh 30d. Refresh rotates access tokens transparently in the Dio interceptor.
- Phone formats: India `+91` + 10 digits (starts 6–9); UAE `+971` + 9 digits (starts 5).
- Webhooks (`/webhook/traccar`, `/webhook/traccar/alarm`) authenticated by a **static shared-secret header** (`X-Traccar-Secret`, constant-time compared), never JWT. NB: stock Traccar's JSON forwarder can only send a fixed header — it cannot HMAC-sign the body — so auth = secret header + network trust (backend not publicly reachable).
- Internal device endpoints (`/location/update`, `/sos/trigger`) use a **device token**, not JWT.
- School admins authenticate by **email + password** (bcrypt), separate from parent OTP.

---

## 8. Key Environment Variables

```
DATABASE_URL, REDIS_URL
FIREBASE_CREDENTIALS_JSON, FIREBASE_DATABASE_URL
TRACCAR_URL, TRACCAR_API_USER, TRACCAR_API_PASSWORD, TRACCAR_WEBHOOK_SECRET
JWT_SECRET, JWT_ALGORITHM=HS256, JWT_ACCESS_EXPIRE_MINUTES=1440, JWT_REFRESH_EXPIRE_DAYS=30
MSG91_AUTH_KEY, TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM_NUMBER
RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET, R2_ENDPOINT
GOOGLE_MAPS_API_KEY
BACKEND_URL, ALLOWED_ORIGINS, ENVIRONMENT
```

---

## 9. Redis Key Reference

```
location:child:{child_id}:latest        {lat,lng,device_id,battery,ts}   24h
location:device:{device_id}:latest       {lat,lng,battery,ts}             24h
device:{device_id}:online                "1"                              5min sliding
device:{device_id}:lastseen              epoch (receipt time)             24h
device:{device_id}:status                "online"/"offline"               24h
traccar_dev:{traccar_id}                 {device_id,child_id}             1h
geofence:{child_id}:{fence_id}:inside     "true"/"false"                  72h
geofence_debounce:{child_id}:{fence_id}   "1"                             5min
sos:{child_id}:active                     "1"                             until resolved
battery_alerted:{device_id}               "1"                             4h
speed_count:{child_id}                    int                             90s
speed_alerted:{child_id}                  "1"                             10min
sound_sessions:{child_id}                 count                           until midnight
rate:otp:{phone}                          count                           1h
rate:otp:ip:{ip}                          count                           1h
denylist:access:{jti}                     "1"                             access token remaining life (≤24h)
denylist:refresh:{jti}                    "1"                             refresh token remaining life (≤30d)
batch:locations                           list<json>                      flush 5s
izylrn_status:{child_id}                  {studying,subject,started}       4h
```

---

## 10. Subscription Tiers (business rules)

| | Free | Basic ₹99/AED9 | Premium ₹199/AED19 | School |
|--|--|--|--|--|
| Children | 1 | 3 | Unlimited | 500+ |
| Devices/child | 1 | 2 | 3 | 2 |
| History | 24h | 7d | 30d | 90d |
| Geofences | 1 | 5 | Unlimited | Unlimited |
| Guardians | 0 | 2 | 5 | Teachers |

Premium-only: Safe Routes, Polygon zones, 30-day history, Weekly PDF, Teen Mode, Crash Detection, AI anomaly, Emergency Contacts, Wearable sync.
Basic+: Sound Around, Two-way Call, School Mode, Speed Alert, Pickup, Watch Removed, Chat, Share Link, Safe Addresses.

---

## 11. Development Workflow

- **One feature per session.** Never build multiple features in one prompt.
- **Backend-first:** build + test the API before any Flutter UI.
- **Tests alongside code** — never commit untested code. `pytest` + `pytest-asyncio`; mock Traccar, FCM, Firebase, Redis, MSG91, Twilio.
- **Feature branches** — never develop on `main`. Each sprint ends with a deployable build.
- **Session start:** read this file → relevant `app/models/` → latest `alembic/versions/` → similar existing feature for patterns.
- Keep `backend/db/schema.sql` as the human-readable canonical reference; the source of truth executed against the DB is the Alembic migrations (kept in sync).

---

## 12. Important Rules for the AI (you) when generating code

1. **Obey the locked decisions in §3** — don't reintroduce DECIMAL lat/lng, JSONB geofence schedule, owner FK on children, or media-relay audio.
2. **Use the exact API envelope** (§6) for every endpoint — no ad-hoc response shapes.
3. **Never put geofence/speed/battery checks inline** in the request path — use `BackgroundTasks` (§4).
4. **Always async** in the backend; never call sync DB/HTTP in an async handler.
5. **UUIDs + UTC + soft-delete filters** by default in every model and query.
6. **Validate inputs to the exact rules** in `User_Journey.docx` and return the specified error `code` + message.
7. **Mock all external services in tests.** No live calls to Traccar/FCM/Firebase/OTP gateways in the test suite.
8. **Webhooks are secret-key authed, not JWT.** Device endpoints use device tokens. Don't apply `get_current_user()` to them.
9. **Tier-gate with `require_tier(...)`** returning 402 — never silently allow over-limit actions.
10. **When a spec is ambiguous, stop and ask** — do not guess on product behavior. Cross-reference `docs/` first.
11. **Keep this file updated** when a new decision is locked, so it stays the single source of truth.

---

*IzySafe v1.0 — maintained for AI-assisted development. Last updated: Sprint 0.*
