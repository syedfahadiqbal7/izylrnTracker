-- ============================================================================
-- IzySafe — Canonical Database Schema (v1.0)
-- ============================================================================
-- Source of truth resolution:
--   PRIMARY  : Sprint Plan DDL  (column names, types, soft-delete strategy)
--   MERGED IN: Blueprint.md     (useful columns: altitude, bearing, accuracy,
--                                address, icon/color, notify flags)
--   EXTENDED : User Journey      (all Phase 2 / Phase 3 tables that were
--                                referenced but never defined in any schema)
--
-- Conventions (from CLAUDE.md):
--   * All primary keys are UUID (gen_random_uuid) EXCEPT high-volume append
--     tables (locations, *_events) which use BIGSERIAL for write throughput.
--   * All timestamps are TIMESTAMPTZ, stored in UTC, displayed in user TZ.
--   * Soft deletes (deleted_at) on user-owned root entities: users, children,
--     devices. Everything else hard-cascades from those.
--   * Status / type fields use VARCHAR + CHECK (not native ENUM) so they can be
--     altered in a migration without a table rewrite.
--   * lat/lng use DOUBLE PRECISION everywhere (see DESIGN NOTE 1).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. Extensions
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
-- NOTE: btree_gist is only needed if we later add exclusion constraints; skipped.

-- ----------------------------------------------------------------------------
-- DESIGN NOTE 1 — lat/lng type: DOUBLE PRECISION (resolves 3.A #1)
--   Blueprint.md used DOUBLE PRECISION, Sprint DDL used DECIMAL(10,7).
--   Decision: DOUBLE PRECISION. Reasons:
--     - All distance math (Haversine, point-in-polygon) is floating point;
--       storing DECIMAL forces a cast on every geofence check (hot path).
--     - 15–17 significant digits >> the ~7 digits GPS hardware actually emits.
--     - Forward-compatible with PostGIS geography(Point) if we migrate later.
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
-- Shared trigger: keep updated_at fresh
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 1. USERS & AUTH
-- ============================================================================

-- Resolves 3.A #2: canonical column names are the Sprint DDL ones
-- (subscription_tier, subscription_expires_at, country_code default '+91').
CREATE TABLE users (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone                   VARCHAR(20) UNIQUE NOT NULL,        -- E.164, e.g. +9198...
    country_code            VARCHAR(5)  NOT NULL DEFAULT '+91', -- '+91' IN, '+971' UAE
    name                    VARCHAR(100),
    email                   VARCHAR(255),                       -- optional; needed for weekly PDF (F25)
    photo_url               TEXT,
    language                VARCHAR(10) NOT NULL DEFAULT 'en'   -- en | hi | ar  (F23)
                            CHECK (language IN ('en','hi','ar')),
    timezone                VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata',
    subscription_tier       VARCHAR(20) NOT NULL DEFAULT 'free'
                            CHECK (subscription_tier IN ('free','basic','premium','school')),
    subscription_expires_at TIMESTAMPTZ,
    fcm_token               TEXT,
    last_login_at           TIMESTAMPTZ,            -- stamped on OTP verify (Sprint 10)
    -- Notification preferences (User Journey: quiet hours suppress non-SOS alerts)
    quiet_hours_from        TIME,
    quiet_hours_to          TIME,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at              TIMESTAMPTZ                          -- soft delete
);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- OTP one-time codes + brute-force tracking (rate limit counters live in Redis).
CREATE TABLE otp_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone       VARCHAR(20)  NOT NULL,
    otp_hash    VARCHAR(100) NOT NULL,          -- bcrypt hash, never plaintext
    attempts    INTEGER      NOT NULL DEFAULT 0,
    verified    BOOLEAN      NOT NULL DEFAULT FALSE,
    channel     VARCHAR(10)  DEFAULT 'whatsapp' -- whatsapp | sms (which one delivered)
                CHECK (channel IN ('whatsapp','sms')),
    expires_at  TIMESTAMPTZ  NOT NULL,          -- created_at + 10 min
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_otp_phone ON otp_sessions (phone, expires_at);

-- Subscription / billing ledger (Sprint 6). users.subscription_tier is the
-- denormalized "current" state; this table is the authoritative payment history.
CREATE TABLE subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tier            VARCHAR(20) NOT NULL
                    CHECK (tier IN ('basic','premium','school')),
    gateway         VARCHAR(20) NOT NULL                    -- razorpay | stripe
                    CHECK (gateway IN ('razorpay','stripe')),
    gateway_sub_id  VARCHAR(120),                            -- external subscription/order id
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','past_due','cancelled','expired')),
    starts_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_subscriptions_user ON subscriptions (user_id, status);
CREATE TRIGGER trg_subscriptions_updated BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ============================================================================
-- 2. CHILDREN & FAMILY
-- ============================================================================
-- DESIGN NOTE 2 — Ownership model (resolves 3.E #14):
--   children has NO direct owner FK. Ownership/authorization is expressed
--   ENTIRELY through family_members. The creator is inserted as
--   role='parent', is_primary=TRUE, can_manage=TRUE. This cleanly supports
--   "two parents both primary" and guardian sharing without schema change.
--   Tier "max children" is enforced in application code by counting children
--   where the requesting user is the is_primary parent.

CREATE TABLE children (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(100) NOT NULL,
    nickname            VARCHAR(50),
    dob                 DATE,                       -- drives Teen Mode age gate (F30)
    photo_url           TEXT,
    school_name         VARCHAR(200),
    class_grade         VARCHAR(50),
    -- School Mode config (F16) — per child
    school_mode_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    school_hours_from   TIME,
    school_hours_to     TIME,
    school_active_days  INTEGER[] NOT NULL DEFAULT ARRAY[1,2,3,4,5],  -- 1=Mon..7=Sun
    -- Speed Alert config (F15) — per child
    speed_alert_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    speed_threshold_kmh INTEGER NOT NULL DEFAULT 60
                        CHECK (speed_threshold_kmh IN (20,30,40,60,80,100,120)),
    -- Teen Driving Mode (F30) — explicit opt-in
    teen_mode_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at          TIMESTAMPTZ                  -- soft delete (30-day retention)
);
CREATE TRIGGER trg_children_updated BEFORE UPDATE ON children
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE family_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id    UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL DEFAULT 'guardian'
                CHECK (role IN ('parent','guardian','grandparent','teacher','relative')),
    is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
    can_view    BOOLEAN NOT NULL DEFAULT TRUE,    -- see live location
    can_call    BOOLEAN NOT NULL DEFAULT FALSE,   -- two-way call / sound around
    can_manage  BOOLEAN NOT NULL DEFAULT FALSE,   -- edit zones, settings, devices
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (child_id, user_id)
);
CREATE INDEX idx_family_user  ON family_members (user_id);
CREATE INDEX idx_family_child ON family_members (child_id);

-- Guardian invitations (F13). Token-based, 48h expiry.
CREATE TABLE invites (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id    UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    invited_by  UUID NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    phone       VARCHAR(20) NOT NULL,
    role        VARCHAR(20) NOT NULL DEFAULT 'guardian'
                CHECK (role IN ('parent','guardian','grandparent','teacher','relative')),
    can_view    BOOLEAN NOT NULL DEFAULT TRUE,
    can_call    BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage  BOOLEAN NOT NULL DEFAULT FALSE,
    token       VARCHAR(64) UNIQUE NOT NULL,      -- UUID/secrets hex
    accepted    BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_invites_token ON invites (token);

-- ============================================================================
-- 3. DEVICES & PAIRING
-- ============================================================================
CREATE TABLE devices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id        UUID REFERENCES children(id) ON DELETE CASCADE, -- nullable since Sprint 8 (bus devices have none)
    school_id       UUID,   -- bus devices belong to a school; FK → schools(id) added in migration 0006 (schools defined later)
    name            VARCHAR(100) NOT NULL,                 -- "Aryan's Watch"
    device_type     VARCHAR(20)  NOT NULL DEFAULT 'watch'
                    CHECK (device_type IN ('watch','bag_tracker','phone','bus')), -- 'bus' added Sprint 8 (migration 0005)
    imei            VARCHAR(20) UNIQUE NOT NULL,
    traccar_id      INTEGER,                               -- Traccar device id
    model           VARCHAR(100),
    color           VARCHAR(30),                           -- UI badge color
    protocol        VARCHAR(20) DEFAULT 'gt06'             -- gt06 | tk103 | h02
                    CHECK (protocol IN ('gt06','tk103','h02')),
    -- Per-device config (User Journey F9 / F18)
    battery_threshold       INTEGER NOT NULL DEFAULT 20
                            CHECK (battery_threshold IN (10,15,20,30)),
    watch_removed_threshold_min INTEGER NOT NULL DEFAULT 10
                            CHECK (watch_removed_threshold_min IN (5,10,15)),
    watch_removed_enabled   BOOLEAN NOT NULL DEFAULT FALSE, -- F18 opt-in switch (Sprint 7, migration 0003)
    -- Cached status (Redis is source of truth for online; these aid cold loads)
    last_battery    INTEGER CHECK (last_battery BETWEEN 0 AND 100),
    last_seen_at    TIMESTAMPTZ,
    is_online       BOOLEAN NOT NULL DEFAULT FALSE,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,                            -- soft delete
    -- A bus tracker has a school + no child; every other device has a child + no school (Sprint 8, migration 0006).
    CONSTRAINT ck_device_owner CHECK (
        (device_type = 'bus'  AND child_id IS NULL     AND school_id IS NOT NULL)
        OR (device_type <> 'bus' AND child_id IS NOT NULL AND school_id IS NULL)
    )
);
CREATE INDEX idx_devices_child   ON devices (child_id);
CREATE INDEX idx_devices_traccar ON devices (traccar_id);
CREATE TRIGGER trg_devices_updated BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- DESIGN NOTE 3 — Pairing code TTL (resolves 3.B #6):
--   Conflicting docs said 15 min (F6) vs 30 min (F8). Standardized to a single
--   configurable value with a 30-minute DEFAULT (the more forgiving of the two,
--   better UX while a parent fiddles with watch settings). App passes expires_at.
CREATE TABLE pairing_codes (
    code        VARCHAR(8) PRIMARY KEY,                    -- 8-char alphanumeric
    child_id    UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    device_type VARCHAR(20) NOT NULL
                CHECK (device_type IN ('watch','bag_tracker','phone')),
    used        BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 minutes'),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 4. LOCATIONS  (high volume, monthly RANGE partitioning)
-- ============================================================================
-- DESIGN NOTE 4 — locations columns (resolves 3.A #3):
--   Sprint DDL dropped altitude/bearing/address; Blueprint kept them. We KEEP
--   them (all nullable) — they cost nothing when null, and history popups +
--   future analytics want speed/accuracy/address. child_id is DENORMALIZED here
--   (NOT NULL) so per-child history queries never need a devices join.
--
-- DESIGN NOTE 5 — Partitioning (resolves 3.D #12):
--   PARTITION BY RANGE (timestamp), one partition per month. The old docs
--   hardcoded 2025 partitions — WRONG for a June-2026 launch. We ship a
--   create_locations_partition() function + a bootstrap loop covering the
--   current month through +18 months, plus a DEFAULT catch-all so a missing
--   partition can never drop a write. A monthly cron (see deployment) calls the
--   function to roll the window forward.

CREATE TABLE locations (
    id          BIGSERIAL,
    device_id   UUID NOT NULL,                  -- FK omitted on partitioned hot table by design (see note 6)
    child_id    UUID NOT NULL,                  -- denormalized for fast history
    lat         DOUBLE PRECISION NOT NULL,
    lng         DOUBLE PRECISION NOT NULL,
    accuracy    DOUBLE PRECISION,               -- meters
    speed       DOUBLE PRECISION,               -- km/h
    altitude    DOUBLE PRECISION,               -- meters (nullable)
    bearing     DOUBLE PRECISION,               -- degrees (nullable)
    battery     INTEGER CHECK (battery BETWEEN 0 AND 100),
    is_moving   BOOLEAN,
    address     TEXT,                           -- reverse-geocoded, lazy/optional
    timestamp   TIMESTAMPTZ NOT NULL,           -- server-received time (authoritative)
    PRIMARY KEY (id, timestamp)                 -- partition key must be in PK
) PARTITION BY RANGE (timestamp);

-- DESIGN NOTE 6 — No FK on locations.device_id:
--   FKs on a partitioned, batch-inserted hot table add per-row trigger cost and
--   complicate partition detach/archival. Referential integrity is guaranteed in
--   the write path (we only insert for devices we just looked up). Indexes below
--   serve the only two read patterns: per-device trail and per-child trail.
CREATE INDEX idx_locations_device_time ON locations (device_id, timestamp DESC);
CREATE INDEX idx_locations_child_time  ON locations (child_id,  timestamp DESC);

-- Catch-all so a write never fails for a missing month.
CREATE TABLE locations_default PARTITION OF locations DEFAULT;

-- Idempotent monthly partition creator.
CREATE OR REPLACE FUNCTION create_locations_partition(p_year INT, p_month INT)
RETURNS void AS $$
DECLARE
    start_date DATE := make_date(p_year, p_month, 1);
    end_date   DATE := (make_date(p_year, p_month, 1) + INTERVAL '1 month')::DATE;
    part_name  TEXT := format('locations_%s_%s', p_year, lpad(p_month::text, 2, '0'));
BEGIN
    IF to_regclass(part_name) IS NULL THEN
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF locations FOR VALUES FROM (%L) TO (%L)',
            part_name, start_date, end_date);
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Bootstrap: current month (2026-06 at time of writing) through +18 months.
-- Replace the seed date in CI/migration with the real deploy month.
DO $$
DECLARE
    d DATE := date_trunc('month', NOW())::DATE;
    i INT;
BEGIN
    FOR i IN 0..18 LOOP
        PERFORM create_locations_partition(
            EXTRACT(YEAR  FROM d + (i || ' month')::interval)::INT,
            EXTRACT(MONTH FROM d + (i || ' month')::interval)::INT);
    END LOOP;
END $$;

-- ============================================================================
-- 5. GEOFENCES  (circle + polygon + named "safe addresses")
-- ============================================================================
-- DESIGN NOTE 7 — geofence schedule + zone typing (resolves 3.A #4 and #5):
--   Blueprint used a single `schedule JSONB`; Sprint DDL used discrete
--   active_days[]/active_from/active_to. We adopt the DISCRETE columns — they
--   are indexable, validatable, and trivial to query at check time.
--   Sprint DDL also had BOTH zone_type and address_type for the same idea.
--   We COLLAPSE them into one `zone_type`. School Mode keys off zone_type='school';
--   Multiple Safe Addresses (F24) just uses the other values. No separate table.
CREATE TABLE geofences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id        UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,            -- "Home", "School", "Grandma"
    zone_type       VARCHAR(20) NOT NULL DEFAULT 'other'
                    CHECK (zone_type IN ('home','school','tuition','grandparents','sports','other')),
    type            VARCHAR(20) NOT NULL DEFAULT 'circle'
                    CHECK (type IN ('circle','polygon')),
    icon            VARCHAR(30) DEFAULT 'home',
    color           VARCHAR(10) DEFAULT '#4CAF50',
    -- Circle fields
    center_lat      DOUBLE PRECISION,
    center_lng      DOUBLE PRECISION,
    radius_m        INTEGER CHECK (radius_m BETWEEN 50 AND 2000),
    -- Polygon fields (F19): [{ "lat": .., "lng": .. }, ...]
    polygon_points  JSONB,
    address         TEXT,
    -- Notification + schedule
    notify_enter    BOOLEAN NOT NULL DEFAULT TRUE,
    notify_exit     BOOLEAN NOT NULL DEFAULT TRUE,
    -- Default to every day: a zone with no explicit schedule alerts 24/7 (Sprint 3).
    active_days     INTEGER[] NOT NULL DEFAULT ARRAY[1,2,3,4,5,6,7],
    active_from     TIME,
    active_to       TIME,
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    school_id       UUID,   -- attendance anchor; FK → schools(id) added in migration 0004 (schools is defined later)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- A circle must have a center+radius; a polygon must have points.
    CONSTRAINT geofence_shape_valid CHECK (
        (type = 'circle'  AND center_lat IS NOT NULL AND center_lng IS NOT NULL AND radius_m IS NOT NULL)
        OR
        (type = 'polygon' AND polygon_points IS NOT NULL)
    )
);
CREATE INDEX idx_geofences_child ON geofences (child_id) WHERE active;
CREATE TRIGGER trg_geofences_updated BEFORE UPDATE ON geofences
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE geofence_events (
    id          BIGSERIAL PRIMARY KEY,
    child_id    UUID NOT NULL REFERENCES children(id)  ON DELETE CASCADE,
    device_id   UUID         REFERENCES devices(id)    ON DELETE SET NULL,
    geofence_id UUID NOT NULL REFERENCES geofences(id) ON DELETE CASCADE,
    event_type  VARCHAR(10) NOT NULL CHECK (event_type IN ('enter','exit')),
    lat         DOUBLE PRECISION,
    lng         DOUBLE PRECISION,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_geofence_events_child_time ON geofence_events (child_id, timestamp DESC);

-- Pickup detection events (F17). Derived from a school-zone exit in the window.
CREATE TABLE pickup_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id      UUID NOT NULL REFERENCES children(id)  ON DELETE CASCADE,
    geofence_id   UUID         REFERENCES geofences(id)  ON DELETE SET NULL,
    movement_mode VARCHAR(10) CHECK (movement_mode IN ('on_foot','in_vehicle','unknown')),
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_pickup_child_time ON pickup_events (child_id, occurred_at DESC);

-- ============================================================================
-- 6. SAFE ROUTES & SHARE LINKS
-- ============================================================================
CREATE TABLE safe_routes (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id              UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    name                  VARCHAR(100) NOT NULL,
    waypoints             JSONB NOT NULL,                -- [{lat,lng,name?}, ...] min 2
    deviation_tolerance_m INTEGER NOT NULL DEFAULT 200
                          CHECK (deviation_tolerance_m BETWEEN 100 AND 500),
    active_days           INTEGER[] NOT NULL DEFAULT ARRAY[1,2,3,4,5],
    active_from           TIME NOT NULL,
    active_to             TIME NOT NULL,
    active                BOOLEAN NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_safe_routes_child ON safe_routes (child_id) WHERE active;
CREATE TRIGGER trg_safe_routes_updated BEFORE UPDATE ON safe_routes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Public, login-less live tracking links (F22). Token = secrets.token_hex(32).
CREATE TABLE share_links (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id    UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    token       VARCHAR(64) UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    view_count  INTEGER NOT NULL DEFAULT 0,
    revoked     BOOLEAN NOT NULL DEFAULT FALSE,
    created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_share_links_token ON share_links (token);

-- ============================================================================
-- 7. SOS & EMERGENCY
-- ============================================================================
-- DESIGN NOTE 8 — Only ONE active SOS per child (resolves the F3 rule):
--   Enforced by a partial UNIQUE index on (child_id) WHERE status='active'.
CREATE TABLE sos_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id     UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    device_id    UUID         REFERENCES devices(id)   ON DELETE SET NULL,
    lat          DOUBLE PRECISION,
    lng          DOUBLE PRECISION,
    address      TEXT,
    approximate  BOOLEAN NOT NULL DEFAULT FALSE,       -- true if last-known used
    status       VARCHAR(20) NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active','resolved')),
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ,
    resolved_by  UUID REFERENCES users(id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX uq_sos_one_active_per_child
    ON sos_events (child_id) WHERE status = 'active';
CREATE INDEX idx_sos_child_time ON sos_events (child_id, triggered_at DESC);

-- Extra SOS recipients beyond family_members (F31). May be non-app (SMS only).
CREATE TABLE emergency_contacts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id     UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    name         VARCHAR(100) NOT NULL,
    phone        VARCHAR(20)  NOT NULL,
    relationship VARCHAR(30),                          -- relative|neighbor|friend|teacher
    is_app_user  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_emergency_contacts_child ON emergency_contacts (child_id);

-- ============================================================================
-- 8. ALERTS (notification inbox — every push lands here too)
-- ============================================================================
CREATE TABLE alerts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    child_id    UUID         REFERENCES children(id)  ON DELETE CASCADE,
    type        VARCHAR(30) NOT NULL                  -- see CHECK below
                CHECK (type IN (
                    'sos','geofence_enter','geofence_exit','low_battery',
                    'critical_battery','device_offline','speed','watch_removed',
                    'route_deviation','pickup','school_arrival','school_absent',
                    'crash','anomaly','chat_reply','family_join','system',
                    'bus_arrival','bus_boarded')),  -- bus_* added Sprint 8/10 (migrations 0005/0008)
    title       VARCHAR(200),
    body        TEXT,
    data        JSONB,                                -- {geofence_id, device_id, lat, lng, ...}
    read        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_alerts_user_unread ON alerts (user_id, read, created_at DESC);

-- ============================================================================
-- 9. COMMUNICATION (sound, call, chat) — Phase 2
-- ============================================================================
-- Remote ambient listening sessions, kept for privacy audit (F11).
CREATE TABLE audio_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id    UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    device_id   UUID         REFERENCES devices(id)   ON DELETE SET NULL,
    user_id     UUID NOT NULL REFERENCES users(id)    ON DELETE CASCADE,  -- who listened
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_s  INTEGER,                              -- <= 15
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audio_sessions_child_time ON audio_sessions (child_id, started_at DESC);

-- Two-way call log (F12).
CREATE TABLE call_records (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id         UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    device_id        UUID         REFERENCES devices(id)   ON DELETE SET NULL,
    initiated_by     UUID NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    status           VARCHAR(20) NOT NULL DEFAULT 'initiated'
                     CHECK (status IN ('initiated','answered','missed','failed')),
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_seconds INTEGER
);
CREATE INDEX idx_call_records_child_time ON call_records (child_id, started_at DESC);

-- Parent <-> watch text + quick replies (F20).
CREATE TABLE chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id    UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    sender_type VARCHAR(10) NOT NULL CHECK (sender_type IN ('parent','child')),
    sender_id   UUID REFERENCES users(id) ON DELETE SET NULL,   -- null when child/watch
    content     VARCHAR(120) NOT NULL,                          -- 100-char limit + slack
    status      VARCHAR(20) NOT NULL DEFAULT 'sent'
                CHECK (status IN ('queued','sent','delivered','failed')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_chat_child_time ON chat_messages (child_id, created_at DESC);

-- ============================================================================
-- 10. TEEN DRIVING & CRASH — Phase 3
-- ============================================================================
CREATE TABLE trips (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id        UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,
    distance_km     DOUBLE PRECISION,
    max_speed_kmh   DOUBLE PRECISION,
    avg_speed_kmh   DOUBLE PRECISION,
    safety_score    INTEGER CHECK (safety_score BETWEEN 0 AND 100),
    night_driving   BOOLEAN NOT NULL DEFAULT FALSE,
    phone_use_count INTEGER NOT NULL DEFAULT 0,
    sharp_turns     INTEGER NOT NULL DEFAULT 0,
    route           JSONB,                              -- sampled polyline
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_trips_child_time ON trips (child_id, started_at DESC);

CREATE TABLE crash_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id      UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    trip_id       UUID REFERENCES trips(id) ON DELETE SET NULL,
    lat           DOUBLE PRECISION,
    lng           DOUBLE PRECISION,
    g_force       DOUBLE PRECISION,
    status        VARCHAR(20) NOT NULL DEFAULT 'detected'
                  CHECK (status IN ('detected','false_positive','escalated','resolved')),
    detected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at  TIMESTAMPTZ
);
CREATE INDEX idx_crash_child_time ON crash_events (child_id, detected_at DESC);

-- ============================================================================
-- 11. INTEGRATIONS — IzyLrn + Wearables (Phase 3)
-- ============================================================================
-- One-way IzyLrn study-status link (F29). Live status lives in Redis (4h TTL);
-- this table only stores the mapping + webhook auth token.
CREATE TABLE izylrn_links (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id          UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    izylrn_student_id VARCHAR(100) NOT NULL,
    webhook_token     VARCHAR(120) NOT NULL,            -- bearer token issued to IzyLrn
    linked_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (child_id)
);

-- Garmin / Fitbit OAuth (F32). Refresh token MUST be encrypted at app layer.
CREATE TABLE wearable_integrations (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id              UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    provider              VARCHAR(20) NOT NULL CHECK (provider IN ('garmin','fitbit')),
    oauth_refresh_token   TEXT NOT NULL,                -- encrypted ciphertext
    connected_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_sync_at          TIMESTAMPTZ,
    UNIQUE (child_id, provider)
);

-- ============================================================================
-- 12. i18n — translation strings (F23)
-- ============================================================================
CREATE TABLE translations (
    key   VARCHAR(120) PRIMARY KEY,
    en    TEXT NOT NULL,
    hi    TEXT,
    ar    TEXT
);

-- ============================================================================
-- 13. SCHOOL TIER — admin, enrollment, attendance, buses (F26–F28)
-- ============================================================================
CREATE TABLE schools (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    address       VARCHAR(300),                         -- school profile (Sprint 10, migration 0010)
    contact_phone VARCHAR(20),
    contact_email VARCHAR(255),
    timezone    VARCHAR(64) NOT NULL DEFAULT 'Asia/Kolkata',
    holidays    JSONB,                                  -- ["2026-08-15", ...]
    -- Attendance status thresholds (configurable per school, F27)
    on_time_before     TIME NOT NULL DEFAULT '09:00',
    late_until         TIME NOT NULL DEFAULT '11:00',
    arrival_window_from TIME NOT NULL DEFAULT '07:00',
    school_days INTEGER[] NOT NULL DEFAULT ARRAY[1,2,3,4,5], -- ISO weekdays in session (Sprint 8, migration 0004)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TRIGGER trg_schools_updated BEFORE UPDATE ON schools
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- DESIGN NOTE 9 — School admin auth (resolves part of 3.E #15 sibling issue):
--   School admins authenticate by EMAIL + PASSWORD (separate from parent OTP),
--   per Sprint 9. Hence a dedicated table with a bcrypt password_hash.
CREATE TABLE school_admins (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id     UUID NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(100) NOT NULL,                -- bcrypt
    name          VARCHAR(100),
    role          VARCHAR(20) NOT NULL DEFAULT 'admin'
                  CHECK (role IN ('admin','staff')),
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,                          -- stamped on login (Sprint 10)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Child <-> school opt-in. Parent must grant visibility (privacy default OFF).
CREATE TABLE student_enrollments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id       UUID NOT NULL REFERENCES schools(id)   ON DELETE CASCADE,
    child_id        UUID NOT NULL REFERENCES children(id)  ON DELETE CASCADE,
    class_grade     VARCHAR(50),
    parent_opt_in   BOOLEAN NOT NULL DEFAULT FALSE,        -- school visibility consent
    bus_opt_in      BOOLEAN NOT NULL DEFAULT FALSE,        -- bus tracking consent
    enrolled_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (school_id, child_id)
);
CREATE INDEX idx_enrollments_school ON student_enrollments (school_id) WHERE parent_opt_in;

CREATE TABLE attendance_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id       UUID NOT NULL REFERENCES schools(id)  ON DELETE CASCADE,
    child_id        UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    date            DATE NOT NULL,
    arrival_time    TIMESTAMPTZ,
    departure_time  TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL DEFAULT 'unknown'
                    CHECK (status IN ('on_time','late','absent','unknown','early')),
    total_hours     DOUBLE PRECISION,
    marked_manually BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (school_id, child_id, date)
);
CREATE INDEX idx_attendance_school_date ON attendance_records (school_id, date);

CREATE TABLE drivers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id     UUID NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
    name          VARCHAR(100) NOT NULL,
    phone         VARCHAR(20),
    password_hash VARCHAR(100),                 -- bcrypt of the admin-set access code (Sprint 10; null ⇒ can't log in)
    verified      BOOLEAN NOT NULL DEFAULT FALSE,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,                          -- stamped on driver login (Sprint 10)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Phone is the driver login key → unique among non-null phones (Sprint 10, migration 0007).
CREATE UNIQUE INDEX uq_drivers_phone ON drivers (phone) WHERE phone IS NOT NULL;

CREATE TABLE bus_routes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id     UUID NOT NULL REFERENCES schools(id)  ON DELETE CASCADE,
    name          VARCHAR(100) NOT NULL,                -- "Route A"
    driver_id     UUID REFERENCES drivers(id) ON DELETE SET NULL,
    device_id     UUID REFERENCES devices(id) ON DELETE SET NULL,  -- GPS on the bus
    active_from   TIME,
    active_to     TIME,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE bus_route_stops (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id      UUID NOT NULL REFERENCES bus_routes(id) ON DELETE CASCADE,
    name          VARCHAR(100) NOT NULL,
    lat           DOUBLE PRECISION NOT NULL,
    lng           DOUBLE PRECISION NOT NULL,
    seq           INTEGER NOT NULL,                     -- ordering
    scheduled_at  TIME,
    UNIQUE (route_id, seq)
);

CREATE TABLE bus_assignments (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id      UUID NOT NULL REFERENCES bus_routes(id) ON DELETE CASCADE,
    child_id      UUID NOT NULL REFERENCES children(id)   ON DELETE CASCADE,
    stop_id       UUID REFERENCES bus_route_stops(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (route_id, child_id)
);

-- Driver-run trips + manual pickup confirmations (Sprint 10, migration 0008).
CREATE TABLE bus_trips (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route_id    UUID NOT NULL REFERENCES bus_routes(id) ON DELETE CASCADE,
    driver_id   UUID REFERENCES drivers(id) ON DELETE SET NULL,
    status      VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active','ended')),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_bus_trip_active_route ON bus_trips (route_id) WHERE status = 'active';
CREATE INDEX idx_bus_trips_driver ON bus_trips (driver_id);

CREATE TABLE bus_boardings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id     UUID NOT NULL REFERENCES bus_trips(id) ON DELETE CASCADE,
    child_id    UUID NOT NULL REFERENCES children(id)  ON DELETE CASCADE,
    stop_id     UUID REFERENCES bus_route_stops(id) ON DELETE SET NULL,
    boarded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (trip_id, child_id)
);

-- School-scoped audit trail of sensitive actions (Sprint 10, migration 0009).
CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    school_id   UUID REFERENCES schools(id) ON DELETE SET NULL,  -- scopes the school-admin audit query
    actor_type  VARCHAR(20) NOT NULL,                 -- school_admin | driver | parent | system
    actor_id    UUID,
    action      VARCHAR(50) NOT NULL,                 -- dotted, e.g. admin.deactivate
    entity_type VARCHAR(40),
    entity_id   UUID,
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_school_time ON audit_log (school_id, created_at DESC);
CREATE INDEX idx_audit_actor ON audit_log (actor_id);

-- ============================================================================
-- END OF SCHEMA
-- Total tables: 33 (12 core + safe_routes + share_links + 19 Phase 2/3 & school)
-- ============================================================================
