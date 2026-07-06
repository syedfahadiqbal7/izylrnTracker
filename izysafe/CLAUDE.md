# IzySafe — Project Context for Claude

> Single source of truth for AI-assisted development. Read this first, every session,
> alongside the detailed specs in `../docs/`. If anything here conflicts with an older
> file in `docs/`, **this file wins** — it encodes the Sprint-0 resolutions.

---

## 0. Current State (update each sprint; keep terse)

- **Done & on `main` (Sprints 0–9, PR #1–9):** infra/schema · Auth/Family · location Flow A · geofences Flow B · SOS+Alerts · Audio · Payments+Celery · **Phase-1 consumer (S7):** Safe Routes+deviation, Pickup F17, Share Link+public track, Watch-Removed, Safe Addresses, Chat · **School B2B (S8):** admin auth, enrollment+opt-in, attendance, bus roster+live tracking · **School-admin lifecycle (S9):** password reset, self-service, admin management. **DB at migration `0009`.** Per-sprint detail lives in git history/PRs, not here.
- **In flight (Sprint 10, branch `sprint-10-driver-auth`):** Slice 1+1b (Driver app) + Slice 2 (Audit log) **merged via PR #10**; **Slice 3 (Attendance reporting/export) built + committed on the branch (amends PR #10).**
- **Sprint 11 — frontends + i18n (branch `frontend-admin-panel`, PR #11, NOT merged). DB now at `0018`. 709 backend tests pass.** Two new apps + a dynamic i18n system, all backend-first (most endpoints pre-existed; new backend work was additive migrations 0010–0018 + a few read/CRUD endpoints).
  - **School Admin Web Panel** (`izysafe/web-admin/`, React 18 + Vite 6 + TS + Tailwind + shadcn/ui + TanStack Query + axios; Leaflet/OSM for maps — keyless, pending `GOOGLE_MAPS_API_KEY`). 9 pages (Dashboard, Live Tracking, Attendance, Reports, Roster, Routes&Buses, Drivers, Audit, Settings) + **Menu Management**. JWT vs `/schools/auth/*`, single-flight refresh-on-401. Prod-ready (Dockerfile→nginx same-origin `/api`, `docker-compose.prod.yml`, `DEPLOY.md`). Demo login `panel-demo@school.test` / `demopass123`.
  - **Parent Mobile App** (`izysafe/flutter/`, Flutter 3.44, **Riverpod 2.6.1 [PIN — `pub add` grabs Riverpod 3 which drops StateNotifier]**, Dio+GoRouter+flutter_secure_storage, **flutter_map/OSM** [not google_maps_flutter — keyless, pending Maps key; map layer isolated for later swap]). Slices: 1 auth(OTP)+children · 2 Live Map(location/geofences/bus-ETA/SOS/emergency) · 3 Alerts inbox+FCM seam · 4 Settings/Profile · 5 Safe Zones CRUD · 6 **Device Pairing & Mgmt** (pair a tracker → registers it in Traccar so Flow A resolves; list w/ live online+battery, edit name/colour/battery-threshold/watch-removed, unpair) · 7 **Share Links** (create Basic+ time-limited public track link {1/8/24h}, QR + copy sheet, active-link list w/ expiry countdown + view-count + revoke). Entries: Live-Map top-bar watch + share-location icons → `/child/:id/devices`, `/child/:id/share`. All screens en/hi/ar. **NEW dep `qr_flutter ^4.1.0`** (riverpod exact-pin held).
  - **i18n + dynamic menus (F23):** wide `translations` table (`key`+`en/hi/ar`+`updated_at`) + `menu_items` table (admin-managed nav). **Public** `GET /i18n/locales`, `GET /i18n/{locale}` (English-fallback bundle, no auth). **Admin** (role=admin) `/schools/localization` + `/schools/menu-items` CRUD; `GET /schools/menu` = caller's role-filtered nav. Both frontends load `t(key,fallback)` from the bundle; **Arabic ⇒ RTL** app-wide. Translations/menus are **app-wide config, not school-scoped** (mgmt gated role=admin; no super-admin role yet). Migrations 0012–0018 seed ~311 strings (idempotent `ON CONFLICT`; `alert_type.*` keys use the EXACT `Alert.type` values; 0017 = `devices.*`, 0018 = `share.*`+`track.*`).
  - **Pending creds → documented graceful seams (no-op until configured):** Firebase RTDB live-stream (app uses REST `GET /children/{id}/location/latest` poll fallback), `firebase_messaging` FCM (PushService.init no-op; `registerToken`→`PUT /auth/me/fcm-token` + deep-link routing are real), `google_maps_flutter` (using flutter_map). **Flutter CanvasKit web: `preview_screenshot` TIMES OUT + canvas not DOM-drivable + secure-storage=encrypted IndexedDB (can't inject session) → verify via DOM-eval boot check + HTTP flow (curl) + analyze/test/build, NOT click-through.**
  - **Device Pairing backend (Sprint 11, this slice — NEW, not pre-existing):** `devices.py` router — `POST/GET /children/{id}/devices`, `GET/PUT/DELETE /devices/{id}` (`DeviceService`, mirrors geofence CRUD). Pairing registers the tracker in Traccar (`TraccarGateway.create_device`→`POST /api/devices`, returns `traccar_id`; `delete_device` on unpair) — **graceful seam: unconfigured/failed Traccar ⇒ null `traccar_id`, pairing still succeeds locally**. Per-child device tier gate `DEVICE_LIMITS {free1/basic2/premium3/school2}` counted over primary parent (402 `DEVICE_LIMIT_REACHED`); IMEI globally unique (409 `IMEI_TAKEN`); manage-perm required (404 non-member / 403 no-manage); soft-delete. Live `is_online` from Redis on read. Bus devices stay school-scoped under `/schools/*` (never here).
  - **Share Links public page (Sprint 11 Slice 7 — NEW backend):** JSON API pre-existed (`/children/{id}/share-links` CRUD + public `/share/{token}`, Basic+, IP-rate-limited, D10 name+fix-only). Added the missing **public HTML tracking PAGE** at root `GET /track/{token}` (`app/api/public_track.py`, `HTMLResponse`, included in `main.py` WITHOUT the `/api/v1` prefix). Static shell — **token read from URL in JS, never server-interpolated (no XSS surface)**; polls `/api/v1/share/{token}` + `/api/v1/i18n/{lang}` client-side; Leaflet/OSM (keyless); `?lang=en|hi|ar` (RTL for ar). `share_link_base_url` (default `https://izysafe.app/track`) must route `/track/*` → backend in prod; dev = `http://localhost:8000/track/{token}`.
  - **Remaining (parent app, backends exist):** Chat, Pickup, Sound Around/Two-way Call (needs watch hardware), Teen Mode. **i18n long-tail:** web-admin deep dialog/sub-component literals still English (editable via Localization panel).
- **Attendance reporting (S10 Slice 3):** read-only rollups over existing `attendance_records` (incl. sweep-written `absent` rows), opted-in students only, joined via `AttendanceService._enroll_join()`. `GET /schools/attendance/report` → date-range summary (`by_status` counts + per-student rollup; **present = on_time+late+early**, rate = present/records) and `GET /schools/attendance/export` → flat per-record CSV register (`text/csv` attachment). Both allow **admin OR staff** (operational data). Range guard: `to ≥ from` else 422 `INVALID_RANGE`; span ≤ 366 days else 422 `RANGE_TOO_LARGE`.
- **Multi-identity auth (S8–S10):** three JWT identities share the HS256/denylist infra, distinguished by an access-token **`scope`** claim: parent (OTP, no scope) · **school_admin** (email+password) · **driver** (phone+admin-set code). Each `get_current_*` dep checks its scope + loads an `active` row; deactivating a school_admin/driver blocks login **and** live tokens (both filter `active`). School endpoints under `/schools/*`; driver under `/drivers/*`. `EmailGateway` (SMTP, no-op when unconfigured) added S9. **Privacy backbone (S8):** a school sees a child only via a `parent_opt_in=TRUE` `student_enrollments` row (`EnrollmentService.require_enrolled_child` → 404 otherwise); `bus_opt_in` is separate.
- **Migration convention (LEARNED — critical):** migration `0001` runs `db/schema.sql` verbatim, then later migrations ALTER on top, and `schema.sql` is kept as the full canonical schema. So every later migration MUST be idempotent (`ADD COLUMN/CREATE TABLE/INDEX IF NOT EXISTS`, guarded `ADD CONSTRAINT` via `DO $$`), and NO forward FK refs in `schema.sql` (declare the col bare, add the FK in the migration). **Always verify a new migration with a scratch-DB fresh `alembic upgrade head`** (`CREATE DATABASE izysafe_fresh` + run with `DATABASE_URL` overridden). 0003 was retro-fixed for this.
- **Audit (S10):** `AuditService.log(session, ...)` adds an `audit_log` row to the **caller's session** (atomic with the action); never logs secrets. `GET /schools/audit` is role='admin' only, school-scoped, filtered+paginated. `last_login_at` on school_admins/drivers/users, stamped on each login.
- **Payment invariants (Sprint 6):** tiers are purchasable via **two gateways routed by `country_code`** (India→Razorpay, UAE→Stripe) behind one `PaymentService` returning a **unified checkout shape** (`gateway`/`reference_id`/`checkout_url`/`key_id`/`status`). Activation is **webhook-driven only** (Decision D) — `POST /subscriptions/checkout` starts a recurring subscription but grants nothing; the signature-verified webhook (`/webhook/razorpay` HMAC-SHA256, `/webhook/stripe` `Stripe-Signature`) is the **single writer** of subscription state (`SubscriptionWebhookService`, one `apply_*` per gateway sharing a gateway-parametrized `_activate`). `{user_id, tier}` rides in gateway metadata (Razorpay `notes` / Stripe `subscription_data.metadata`) so the payer resolves **statelessly** (no local pending row — `subscriptions.status` CHECK has no 'created'). Webhooks are **idempotent** per event id (Redis `payevt:{gw}:{id}`); bad signature → 401; a genuine DB error propagates (5xx) so the gateway retries; unresolved/duplicate → 200. Confirmation alert uses type `system` (no new alert type). Downgrade is **non-destructive** (Decision E): `effective_tier` treats a lapsed tier as free on read; the daily expiry sweep makes it durable + notifies; existing resources kept, new over-limit creation blocked. Gateways never raise (→ None → 502). Outbound *checkout* calls need real gateway test API keys (pending, like the watch spike); webhook + job paths are live-verified.
- **Celery invariants (Sprint 6, §4):** scheduled/heavy jobs only (in-request checks stay FastAPI BackgroundTasks; batch writer stays a lifespan loop). `app/worker/` = Celery app + beat (broker/backend default to `redis_url`) + task wrappers. Tasks are **sync** → run their async service via `asyncio.run` on a **fresh NullPool engine per run** (never bind the app engine to a throwaway loop). Job logic lives in services with a `session_factory` (`SubscriptionExpiryService`, `PartitionService`, `PurgeService`), unit-tested directly via `NonClosingSession`. `celery-worker` + `celery-beat` compose services. Beat: expiry sweep daily 02:00, purge daily 03:00, partition roll-forward monthly. Partition roll-forward is idempotent (`create_locations_partition` no-ops if present); purge hard-deletes soft-deleted rows > 30d (FK cascades).
- **Audio invariants (Sprint 5, §3.12):** **no media server** — the backend only *gates + issues a Traccar SIM command + logs*; the watch dials the requesting parent over its own SIM (audio never touches our servers). `TraccarGateway.send_command` → `POST {TRACCAR_URL}/api/commands` (basic auth) with a **non-null `description`** (Traccar queues offline-device commands into a NOT NULL column → 400 without it); never raises (→ False on unconfigured/reject/network). Command strings (`MONITOR,<phone>#` / `CALLBACK,<phone>#`) are GT06-**model-specific**, held in config templates. Shared gates (`_AudioFeatureService`): can_call family perm → Basic+ over the **primary parent** → watch online (Redis `device:{id}:online`, needs a `traccar_id`). Sound Around adds a **3/child/day** quota (`sound_sessions:{child}`, midnight TTL in primary-parent tz); Two-way Call adds a **no-active-call** guard (Redis `call:{child}:active`, 5-min self-expiring — no hang-up signal exists). Watch dials the **requesting user's** phone; quota/marker/audit-row advance **only on successful dispatch**. Outcome (answer/duration/miss) **not observable** backend-side → `duration_*` NULL, `call_records.status` stays `'initiated'`. Consent screen + mic indicator are app-side (§3.13); true end-to-end delivery pending the `HARDWARE_SPIKE.md` §4 physical-watch spike.
- **SOS/Alerts invariants (Sprint 4):** SOS trigger = secret-authed `POST /webhook/traccar/alarm` (NOT JWT); resolve inline, fan-out in a webhook `BackgroundTask` via `SosAlarmService` (own session_factory). Dedup = Redis `sos:{child}:active` + DB pre-check, hard-guarded by the one-active-per-child partial unique index. SOS FCM is **urgent** (`FcmGateway.send(urgent=True)` → MAX priority, bypasses DND/School Mode) to family + **app-user emergency contacts** (matched by phone, family excluded). Location falls back to last-known Redis fix → `approximate=true`. `PUT /sos/{id}/resolve` (any family member — Decision F) clears the Redis marker + flips Firebase `sos/{child}/active` false. Emergency Contacts CRUD is **Premium** (`is_app_user` derived by phone). Alerts inbox is **per-user** (`AlertInboxService`, scoped to `Alert.user_id`): `GET /alerts` (paginate + `?unread=`/`?child_id=`), `PUT /alerts/{id}/read`, `PUT /alerts/read-all`. Request-path services `SosService`/`EmergencyContactService`/`AlertInboxService` vs. background `SosAlarmService` (mirrors the geofence split).
- **Geofence invariants (Sprint 3):** breach detection (`GeofenceBreachService.check_all_fences`) runs **only** in the webhook `BackgroundTask`, skipped on stale fixes. Per-fence state `geofence:{child}:{fence}:inside` (72h) is **always advanced** (suppressed transitions don't re-fire); first ping is **baseline** (no alert). Fire gated by notify flags → fence schedule (active_days/from/to in the **primary parent's tz**) → **School Mode** (Basic+: school-zone enter→`school_arrival`, non-school muted during school hours) → 5-min debounce. The active-fence bundle (fences + child name + parent tz/tier + school config) is **cached in `active_fences:{child}`**, invalidated by CRUD — common pings touch Redis only. Geometry is **pure Python** (haversine/ray-casting, `app/core/geometry.py`). Zone tier-gate counts over the **primary parent** (per-child limit; polygon=Premium+). `geofences.active_days` DEFAULT is **all 7 days** (migration `0002`); child `school_active_days` stays Mon–Fri.
- **Real-time pipeline invariants (Sprint 2):** webhook `/webhook/traccar` hot path is **Redis-only** (latest cache, `device:{id}:online` 5min, `device:{id}:lastseen`, `batch:locations` LPUSH) and **always 200** (ignore unknown-device/invalid so Traccar's queue can't back up). All checks (battery/speed/online-reconcile/geofence) run in **webhook `BackgroundTasks`**; `BatchWriter` (5s) + `DeviceStatusMonitor` (60s) are **lifespan loops**. External gateways `RealtimeGateway`/`FcmGateway` wrap **sync firebase-admin in `asyncio.to_thread`**, **never raise**, no-op when Firebase unconfigured. Alert fan-out only via `AlertService` (`notify_family`/`notify_user` → inbox row per member + multicast FCM; **caller owns the txn**). Background-task services take a **session_factory** (own session; request session is gone by then) — tested via `NonClosingSession` + `dependency_overrides` of `get_*_service`/`get_fcm_gateway`.
- **Run:** `cd izysafe && docker compose up -d` (postgres, redis@6380→6379, traccar, backend@8000, celery-worker, celery-beat). Tests: `docker compose exec -T backend pytest -q` (or `run --rm`). `celerybeat-schedule` is a gitignored runtime artifact.
- **Auth runtime invariants:** JWT HS256 + Redis denylist (`denylist:{access,refresh}:{jti}`) + refresh rotation. `get_current_user` is **fail-open** on Redis down; refresh/logout **fail-closed**. Webhooks/device endpoints are NOT JWT (secret-key / device token).
- **Authorization invariant:** all child access flows through `family_members` (no owner FK). Non-members get **404** (not 403). Primary parent is protected (can't be removed/demoted). Tier limits counted over the **primary parent**, incl. pending invites.
- **Validation pattern:** structural/enum → Pydantic (422 `VALIDATION_ERROR`); semantic/business → service raises `APIException` with a precise code (e.g. `INVALID_PHONE`, `CHILD_LIMIT_REACHED`).
- **Test isolation:** module-level async engine uses **NullPool** (function-scoped loops); per-test session bound to one connection with `join_transaction_mode="create_savepoint"` + outer rollback; fakeredis + fake gateways via `dependency_overrides`.
- **Deferred / pending creds (all graceful no-ops until configured):** outbound payment *checkout* (Razorpay/Stripe test keys), reverse-geocoding (`GOOGLE_MAPS_API_KEY`), email delivery (`SMTP_*`), and watch hardware paths (Watch-Removed alarm strings, Chat text command + inbound, audio) — all built+tested behind gateways that no-op when unconfigured; real delivery awaits creds / the `HARDWARE_SPIKE.md` physical-watch spike. Weekly PDF (F25) still deferred (needs R2 + PDF renderer). Global session-invalidation-on-password-reset skipped (no token-version column).
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
active_fences:{child_id}                  {tz,child_name,tier,school,fences[]}  1h (CRUD-invalidated)
sos:{child_id}:active                     "1"                             until resolved
battery_alerted:{device_id}               "1"                             4h
speed_count:{child_id}                    int                             90s
speed_alerted:{child_id}                  "1"                             10min
sound_sessions:{child_id}                 count                           until midnight (parent tz)
call:{child_id}:active                    "1"                             5min (Two-way Call in-progress guard)
payevt:{gateway}:{event_id}               "1"                             24h (payment webhook idempotency)
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
