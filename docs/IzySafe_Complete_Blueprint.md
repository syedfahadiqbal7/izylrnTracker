# IzySafe — Complete Product Blueprint
**Version 1.0 | Prepared for: Faraz | Stack: Flutter + FastAPI + PostgreSQL + Firebase**

---

## 1. Market Landscape — Competitor Analysis

| App | GPS Watch Support | Multi-Device/Child | India Pricing | Watch Price | Privacy | Unique Feature |
|---|---|---|---|---|---|---|
| **Life360** | ❌ Phone only | ✅ Circles | $4.99–19.99/mo | N/A | ⚠️ Sells data in free | Crash detection |
| **FindMyKids** | ✅ GPS watches | ✅ | $3–6/mo | Watch sold separately | ✅ | Sound around |
| **FamiSafe** | ⚠️ Limited | ✅ | $5–10/mo | N/A | ✅ | Social media monitoring |
| **Google Family Link** | ❌ | ✅ | Free | N/A | ✅ | Free, Android native |
| **iSharing** | ❌ | ✅ | $2–4/mo | N/A | ✅ | Closest Life360 clone |
| **GeoZilla** | ❌ | ✅ | $3–5/mo | N/A | ✅ | Driving behavior |
| **IzySafe (Ours)** | ✅ Native | ✅ Multi-device | ₹99–199/mo | ₹1,800 bundle | ✅ No ads | IzyLrn integration |

### Key Gaps in Market IzySafe Can Fill
1. No app offers **affordable hardware + app bundle for India/UAE** market together.
2. Life360 (market leader) has **zero GPS watch support** — huge gap.
3. No app has **school attendance + GPS** in one product.
4. No app supports **multi-device per child** (watch + bag tracker simultaneously).
5. No app supports **Hindi/Arabic** natively for South Asia + MENA.

---

## 2. Complete Feature Specification

### Phase 1 — MVP Core (Build First, Weeks 1–8)

| # | Feature | Description | Priority |
|---|---|---|---|
| 1 | **Real-time location** | Live GPS on map, updates every 30s | 🔴 Must |
| 2 | **Location history** | 7-day trail with route playback | 🔴 Must |
| 3 | **SOS button** | Panic button on watch → instant parent alert + location | 🔴 Must |
| 4 | **Geofence (circle)** | Home + School zones, enter/leave alerts | 🔴 Must |
| 5 | **Multi-child dashboard** | Parent sees all kids on one map | 🔴 Must |
| 6 | **Multi-device per child** | Watch + bag tracker tracked separately | 🔴 Must |
| 7 | **OTP login** | WhatsApp/SMS OTP, no email needed | 🔴 Must |
| 8 | **QR pairing** | Parent scans QR code to pair new device | 🔴 Must |
| 9 | **Low battery alert** | FCM push when watch battery < 20% | 🔴 Must |
| 10 | **Device status** | Online/Offline badge + last seen time | 🔴 Must |

### Phase 2 — Differentiators (Weeks 9–14)

| # | Feature | Description | Priority |
|---|---|---|---|
| 11 | **Sound around** | Parent can remotely activate watch mic (1-way listen) | 🟠 High |
| 12 | **Two-way call** | Parent ↔ Watch call via app | 🟠 High |
| 13 | **Family sharing** | Add grandparents/guardians as viewers | 🟠 High |
| 14 | **Safe routes** | Define expected route, alert if deviated | 🟠 High |
| 15 | **Speed alert** | Alert if child in vehicle >60km/h | 🟠 High |
| 16 | **School mode** | Show "In School ✅" instead of exact coords during school hours | 🟠 High |
| 17 | **Pickup detection** | Auto-detect when child leaves school, notify parent | 🟠 High |
| 18 | **Watch removed alert** | Accelerometer detects watch taken off | 🟠 High |
| 19 | **Geofence (polygon)** | Draw custom zone shape on map | 🟡 Medium |
| 20 | **In-app chat** | Parent ↔ Child text messages | 🟡 Medium |
| 21 | **30-day history** | Extended location history for premium | 🟡 Medium |
| 22 | **Location sharing link** | One-time shareable link (e.g. for driver) | 🟡 Medium |
| 23 | **Hindi/Arabic UI** | Full i18n for IN + UAE markets | 🟡 Medium |
| 24 | **Multiple safe addresses** | Home, School, Tuition, Grandma's | 🟡 Medium |
| 25 | **Weekly safety report** | PDF report emailed to parent every week | 🟡 Medium |

### Phase 3 — Platform Scale (Weeks 15–22)

| # | Feature | Description | Priority |
|---|---|---|---|
| 26 | **School dashboard** | Web admin for schools — all students on one map | 🟡 Medium |
| 27 | **Attendance tracking** | Auto check-in when child enters school geofence | 🟡 Medium |
| 28 | **Driver management** | Assign school bus driver, parents see bus location | 🟡 Medium |
| 29 | **IzyLrn integration** | "Studying 📚" status synced from IzyLrn app | 🟢 Later |
| 30 | **Teen driving mode** | Speed reports, phone usage for 16–18 yr olds | 🟢 Later |
| 31 | **Emergency contacts** | SOS alerts to grandparent + parent simultaneously | 🟢 Later |
| 32 | **Wearable sync** | Future: integrate with Garmin/Fitbit Kids | 🟢 Later |
| 33 | **AI route anomaly** | ML detects unusual patterns → alert | 🟢 Later |
| 34 | **Offline GPS caching** | Watch stores last 100 points if no connectivity | 🟢 Later |
| 35 | **Crash detection** | Sudden acceleration change → auto SOS (teen mode) | 🟢 Later |

---

## 3. Multi-Device Architecture

### Concept
One child can have **up to 3 devices** (Free: 1, Basic: 2, Premium: 3):
- **Watch** — primary, real-time GPS (30s intervals)
- **Bag tracker** — backup, battery-optimized (5min intervals)
- **Phone app** — for older kids (12+) who carry phones

### Parent Dashboard Behavior
```
Parent sees:
┌─────────────────────────────────────────┐
│  Aryan (Grade 5)              🔋82%  ●  │
│  📍 Near School, Pune                   │
│  Watch: Active  ●  |  Bag: Active ●    │
│  [View on Map] [Call] [History]         │
└─────────────────────────────────────────┘
```

### "Last Known Location" Logic
- Redis key `location:child:{child_id}:latest` stores the **most recent** location across ALL devices
- Map shows this unified location with device badge indicator
- Tap a device name → filter map to only that device's trail

### Data Model for Multi-Device
```
users (1)
  └── family_members (N)
        └── children (1)
              └── devices (N — watch, bag_tracker, phone)
                    └── locations (N — timestamped GPS records)
```

### Device Failover
- If Watch goes offline, Bag Tracker becomes "primary"
- System detects offline if no update in > 5 minutes → alert parent
- "Last seen: 12 mins ago" shown on badge

---

## 4. Flutter App Architecture

### Folder Structure (Clean Architecture + Riverpod)
```
lib/
├── main.dart
├── bootstrap.dart
├── injection_container.dart          # GetIt dependency injection
│
├── core/
│   ├── api/
│   │   ├── dio_client.dart           # Dio with interceptors
│   │   ├── api_endpoints.dart
│   │   └── interceptors/
│   │       ├── auth_interceptor.dart
│   │       └── error_interceptor.dart
│   ├── auth/
│   │   ├── auth_manager.dart
│   │   └── token_storage.dart        # Hive secure storage
│   ├── firebase/
│   │   ├── firebase_rt_service.dart  # Realtime DB listener
│   │   └── fcm_handler.dart          # Push notification handling
│   ├── location/
│   │   └── location_utils.dart       # Haversine, geofence math
│   └── theme/
│       ├── app_colors.dart
│       └── app_text_styles.dart
│
├── features/
│   ├── auth/
│   │   ├── data/            # OTP models, auth repo impl
│   │   ├── domain/          # Auth usecases, entities
│   │   └── presentation/
│   │       ├── providers/   # Riverpod auth provider
│   │       └── pages/
│   │           ├── phone_input_page.dart
│   │           └── otp_verify_page.dart
│   │
│   ├── dashboard/
│   │   └── presentation/
│   │       ├── dashboard_page.dart   # Main screen with all children
│   │       ├── widgets/
│   │       │   ├── child_summary_card.dart
│   │       │   └── quick_sos_banner.dart
│   │       └── providers/
│   │           └── dashboard_provider.dart
│   │
│   ├── map/
│   │   └── presentation/
│   │       ├── live_map_page.dart    # Google Maps full screen
│   │       ├── history_map_page.dart # Route playback
│   │       └── widgets/
│   │           ├── child_marker.dart
│   │           ├── geofence_circle.dart
│   │           └── device_switcher.dart  # Multi-device tab bar
│   │
│   ├── children/
│   │   └── presentation/
│   │       ├── child_list_page.dart
│   │       ├── add_child_page.dart
│   │       └── child_settings_page.dart
│   │
│   ├── devices/
│   │   └── presentation/
│   │       ├── device_list_page.dart
│   │       ├── add_device_page.dart    # QR scan + pairing code flow
│   │       └── device_detail_page.dart # Battery, status, history
│   │
│   ├── geofence/
│   │   └── presentation/
│   │       ├── geofence_list_page.dart
│   │       ├── create_geofence_page.dart   # Draw circle on map
│   │       └── geofence_events_page.dart   # History of enter/exits
│   │
│   ├── alerts/
│   │   └── presentation/
│   │       ├── alerts_page.dart
│   │       └── widgets/
│   │           └── alert_tile.dart
│   │
│   ├── sos/
│   │   └── presentation/
│   │       ├── sos_active_page.dart    # Full-screen SOS response UI
│   │       └── providers/
│   │           └── sos_provider.dart
│   │
│   ├── family/
│   │   └── presentation/
│   │       ├── family_members_page.dart
│   │       └── invite_guardian_page.dart
│   │
│   └── settings/
│       └── presentation/
│           ├── settings_page.dart
│           ├── subscription_page.dart
│           └── notification_prefs_page.dart
│
└── shared/
    ├── widgets/
    │   ├── izysafe_scaffold.dart
    │   ├── loading_overlay.dart
    │   └── battery_indicator.dart
    └── router/
        └── app_router.dart             # GoRouter
```

### State Management: Riverpod
```dart
// Example: Live location provider
@riverpod
Stream<LocationModel> childLiveLocation(
  ChildLiveLocationRef ref,
  String childId,
) {
  final firebaseService = ref.watch(firebaseRtServiceProvider);
  return firebaseService.locationStream(childId);
}

// Usage in widget:
final location = ref.watch(childLiveLocationProvider(childId));
```

### Key Flutter Packages
```yaml
dependencies:
  # State
  flutter_riverpod: ^2.5.0
  riverpod_annotation: ^2.3.0

  # Network
  dio: ^5.4.0
  retrofit: ^4.1.0

  # Firebase
  firebase_database: ^10.5.0
  firebase_messaging: ^14.9.0
  firebase_core: ^2.30.0

  # Maps
  google_maps_flutter: ^2.6.0
  flutter_polyline_points: ^2.0.0

  # Local storage
  hive_flutter: ^1.1.0
  flutter_secure_storage: ^9.0.0

  # Navigation
  go_router: ^13.2.0

  # Background
  flutter_background_service: ^5.0.5   # if child has phone
  workmanager: ^0.5.2

  # Notifications
  flutter_local_notifications: ^17.2.0

  # UI
  cached_network_image: ^3.3.1
  shimmer: ^3.0.0
  lottie: ^3.1.0

  # QR
  mobile_scanner: ^5.1.0               # QR scan for device pairing
  qr_flutter: ^4.1.0                   # QR generation on device side
```

---

## 5. Backend Architecture (FastAPI)

### Project Structure
```
izysafe-backend/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
│
├── app/
│   ├── main.py                       # FastAPI app entry
│   ├── config/
│   │   ├── settings.py               # Pydantic settings (env vars)
│   │   └── database.py               # SQLAlchemy async engine
│   │
│   ├── api/v1/
│   │   ├── router.py                 # Main v1 router
│   │   ├── auth.py                   # OTP send/verify/refresh
│   │   ├── children.py               # CRUD children
│   │   ├── devices.py                # CRUD devices + pairing
│   │   ├── location.py               # Live + history + batch write
│   │   ├── geofence.py               # CRUD geofences + events
│   │   ├── alerts.py                 # List + mark read
│   │   ├── sos.py                    # Trigger + resolve
│   │   ├── family.py                 # Members + invites
│   │   └── webhook.py                # Traccar webhook receiver
│   │
│   ├── models/                       # SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── child.py
│   │   ├── device.py
│   │   ├── location.py
│   │   ├── geofence.py
│   │   └── sos.py
│   │
│   ├── schemas/                      # Pydantic request/response
│   │   ├── location.py
│   │   ├── geofence.py
│   │   └── ...
│   │
│   ├── services/
│   │   ├── auth_service.py           # OTP generation, JWT
│   │   ├── location_service.py       # Store + retrieve location
│   │   ├── geofence_service.py       # Haversine check on every update
│   │   ├── traccar_client.py         # Calls Traccar REST API
│   │   ├── firebase_service.py       # Writes to Firebase RT DB
│   │   ├── fcm_service.py            # Sends push notifications
│   │   └── sos_service.py            # SOS flow
│   │
│   ├── workers/
│   │   ├── location_processor.py     # Background: bulk location writes
│   │   └── geofence_scheduler.py     # Periodic geofence status check
│   │
│   └── middleware/
│       ├── auth_middleware.py        # JWT validation
│       └── rate_limiter.py           # Slowapi rate limiting
│
└── alembic/                          # DB migrations
    └── versions/
```

### Critical Data Flows

#### Flow 1: Device → Parent Map (Real-time)
```
Watch (GT06 protocol)
  → Traccar Server (Port 5023)
    → Traccar detects position event
      → POST webhook to IzySafe Backend /api/v1/webhook/traccar
        → location_service.process_update()
          → Write to PostgreSQL (async batch)
          → Write to Redis (instant: location:child:{id}:latest)
          → Write to Firebase RT DB (parent app reads this)
            → Parent Flutter App (Stream<Location> via Firebase)
              → Google Maps marker updates in real-time
```

#### Flow 2: Geofence Breach → FCM Alert
```
location_service.process_update(lat, lng, device_id)
  → geofence_service.check_all_fences(child_id, lat, lng)
    → For each active geofence:
      → is_inside_fence(lat, lng, fence) → True/False
        → Compare with previous status (Redis: geofence:{child_id}:{fence_id}:inside)
          → Status changed? (was outside, now inside = ENTER event)
            → geofence_events table: INSERT
            → alerts table: INSERT
            → fcm_service.send_to_all_family_members(child_id, alert)
              → FCM push → Parent phone notification
```

#### Flow 3: SOS Trigger
```
Watch SOS button pressed
  → GT06 alarm packet → Traccar → Webhook
    → sos_service.trigger_sos(device_id, lat, lng)
      → sos_events table: INSERT
      → Firebase RT DB: sos/{child_id} = {active: true, lat, lng}
        → Parent app shows FULL-SCREEN SOS alert immediately
      → fcm_service.send_urgent_sos(all_family_members)
        → High-priority FCM push (bypasses DND mode)
      → Optional: auto-call parent (VoIP integration)
```

---

## 6. Database Schema (PostgreSQL)

```sql
-- =============================================
-- USERS & AUTH
-- =============================================
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone         VARCHAR(20) UNIQUE NOT NULL,
    country_code  VARCHAR(5) DEFAULT 'IN',
    name          VARCHAR(100),
    email         VARCHAR(255),
    photo_url     TEXT,
    language      VARCHAR(10) DEFAULT 'en',
    sub_tier      VARCHAR(20) DEFAULT 'free',   -- free, basic, premium, school
    sub_expires   TIMESTAMPTZ,
    fcm_token     TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE otp_sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone      VARCHAR(20) NOT NULL,
    otp_hash   VARCHAR(100) NOT NULL,
    attempts   INT DEFAULT 0,
    verified   BOOLEAN DEFAULT false,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- CHILDREN
-- =============================================
CREATE TABLE children (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL,
    nickname    VARCHAR(50),
    dob         DATE,
    photo_url   TEXT,
    school_name VARCHAR(200),
    class_grade VARCHAR(20),
    active      BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE family_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id    UUID REFERENCES children(id) ON DELETE CASCADE,
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    role        VARCHAR(20) DEFAULT 'parent',      -- parent, guardian, grandparent, teacher
    is_primary  BOOLEAN DEFAULT false,
    can_view    BOOLEAN DEFAULT true,
    can_call    BOOLEAN DEFAULT false,
    can_manage  BOOLEAN DEFAULT false,             -- edit geofences, settings
    joined_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(child_id, user_id)
);

CREATE TABLE invites (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id    UUID REFERENCES children(id),
    invited_by  UUID REFERENCES users(id),
    phone       VARCHAR(20) NOT NULL,
    role        VARCHAR(20) DEFAULT 'guardian',
    token       VARCHAR(64) UNIQUE NOT NULL,
    accepted    BOOLEAN DEFAULT false,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- DEVICES
-- =============================================
CREATE TABLE devices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id        UUID REFERENCES children(id) ON DELETE CASCADE,
    device_type     VARCHAR(20) DEFAULT 'watch',    -- watch, bag_tracker, phone
    name            VARCHAR(100),                    -- "Aryan's Watch"
    traccar_id      INTEGER,                         -- Traccar device ID
    imei            VARCHAR(20) UNIQUE,
    model           VARCHAR(100),                    -- "Wonlex KT23"
    color           VARCHAR(30),                     -- for UI badge
    active          BOOLEAN DEFAULT true,
    last_seen_at    TIMESTAMPTZ,
    last_battery    INTEGER,                         -- 0-100
    is_online       BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE pairing_codes (
    code        VARCHAR(8) PRIMARY KEY,
    child_id    UUID REFERENCES children(id),
    device_type VARCHAR(20),
    used        BOOLEAN DEFAULT false,
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- LOCATIONS (high-volume, partition by month)
-- =============================================
CREATE TABLE locations (
    id          BIGSERIAL,
    device_id   UUID REFERENCES devices(id),
    lat         DOUBLE PRECISION NOT NULL,
    lng         DOUBLE PRECISION NOT NULL,
    accuracy    FLOAT,
    speed       FLOAT,                               -- km/h
    altitude    FLOAT,
    bearing     FLOAT,
    battery     INTEGER,
    is_moving   BOOLEAN,
    address     TEXT,                                -- reverse geocoded (optional)
    timestamp   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Create monthly partitions
CREATE TABLE locations_2025_01 PARTITION OF locations
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
-- (add partition each month via cron job)

CREATE INDEX idx_locations_device_time ON locations(device_id, timestamp DESC);

-- =============================================
-- GEOFENCES
-- =============================================
CREATE TABLE geofences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id        UUID REFERENCES children(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,           -- "Home", "School"
    icon            VARCHAR(30) DEFAULT 'home',      -- emoji or icon name
    type            VARCHAR(20) DEFAULT 'circle',    -- circle, polygon
    center_lat      DOUBLE PRECISION,
    center_lng      DOUBLE PRECISION,
    radius_m        INTEGER DEFAULT 200,
    polygon_points  JSONB,                           -- [{lat, lng}] array
    address         TEXT,
    color           VARCHAR(10) DEFAULT '#4CAF50',
    notify_enter    BOOLEAN DEFAULT true,
    notify_exit     BOOLEAN DEFAULT true,
    active          BOOLEAN DEFAULT true,
    schedule        JSONB,                           -- {days: [1,2,3,4,5], from: "08:00", to: "15:00"}
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE geofence_events (
    id          BIGSERIAL PRIMARY KEY,
    child_id    UUID REFERENCES children(id),
    device_id   UUID REFERENCES devices(id),
    geofence_id UUID REFERENCES geofences(id),
    event_type  VARCHAR(10) NOT NULL,                -- enter, exit
    lat         DOUBLE PRECISION,
    lng         DOUBLE PRECISION,
    timestamp   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_geofence_events_child_time ON geofence_events(child_id, timestamp DESC);

-- =============================================
-- SOS EVENTS
-- =============================================
CREATE TABLE sos_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id        UUID REFERENCES children(id),
    device_id       UUID REFERENCES devices(id),
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    address         TEXT,
    status          VARCHAR(20) DEFAULT 'active',    -- active, resolved
    triggered_at    TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    resolved_by     UUID REFERENCES users(id)
);

-- =============================================
-- SAFE ROUTES
-- =============================================
CREATE TABLE safe_routes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id    UUID REFERENCES children(id),
    name        VARCHAR(100),                        -- "School Route"
    waypoints   JSONB NOT NULL,                      -- [{lat, lng, name, radius_m}]
    days        INTEGER[] DEFAULT '{1,2,3,4,5}',    -- 1=Mon...7=Sun
    active_from TIME,
    active_to   TIME,
    active      BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================
-- ALERTS & NOTIFICATIONS
-- =============================================
CREATE TABLE alerts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    child_id    UUID REFERENCES children(id),
    type        VARCHAR(30) NOT NULL,     -- sos, geofence_enter, geofence_exit, low_battery, device_offline, speed
    title       VARCHAR(200),
    body        TEXT,
    data        JSONB,                    -- {geofence_id, device_id, lat, lng, ...}
    read        BOOLEAN DEFAULT false,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_user_unread ON alerts(user_id, read, created_at DESC);
```

---

## 7. Complete API Specification

### Base URL: `https://api.izysafe.com/v1`

#### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/send-otp` | Send OTP to phone |
| POST | `/auth/verify-otp` | Verify OTP, get JWT |
| POST | `/auth/refresh` | Refresh access token |
| DELETE | `/auth/logout` | Invalidate token |

#### Children
| Method | Endpoint | Description |
|---|---|---|
| GET | `/children` | List all children for parent |
| POST | `/children` | Add new child |
| GET | `/children/{id}` | Child detail |
| PUT | `/children/{id}` | Update child info |
| DELETE | `/children/{id}` | Soft delete child |

#### Devices (Multi-device per child)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/children/{id}/devices` | List all devices for child |
| POST | `/children/{id}/devices` | Register new device |
| POST | `/devices/pair` | Pair using QR/pairing code |
| PUT | `/devices/{id}` | Rename/update device |
| DELETE | `/devices/{id}` | Remove device |
| GET | `/devices/{id}/status` | Battery, online status |

#### Location
| Method | Endpoint | Description |
|---|---|---|
| POST | `/location/update` | Device → backend (direct, or via Traccar webhook) |
| GET | `/children/{id}/location/live` | Latest location (from Redis, instant) |
| GET | `/children/{id}/location/history` | `?from=&to=&device_id=&limit=` |
| GET | `/children/{id}/location/all-devices` | Latest location per device |

#### Geofences
| Method | Endpoint | Description |
|---|---|---|
| GET | `/children/{id}/geofences` | List geofences |
| POST | `/children/{id}/geofences` | Create geofence |
| PUT | `/geofences/{id}` | Update geofence |
| DELETE | `/geofences/{id}` | Delete geofence |
| GET | `/geofences/{id}/events` | Entry/exit history |

#### SOS
| Method | Endpoint | Description |
|---|---|---|
| POST | `/sos/trigger` | Device triggers SOS |
| GET | `/sos/active` | Get active SOS events |
| PUT | `/sos/{id}/resolve` | Parent marks SOS resolved |

#### Alerts
| Method | Endpoint | Description |
|---|---|---|
| GET | `/alerts` | `?unread=true&child_id=` |
| PUT | `/alerts/{id}/read` | Mark single read |
| PUT | `/alerts/read-all` | Mark all read |

#### Family
| Method | Endpoint | Description |
|---|---|---|
| GET | `/children/{id}/family` | List family members |
| POST | `/children/{id}/family/invite` | Invite guardian by phone |
| GET | `/invites/{token}/accept` | Accept invite link |
| DELETE | `/family/{id}` | Remove family member |

#### Internal (Device/Traccar webhook)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/webhook/traccar` | Traccar position webhook |
| POST | `/webhook/traccar/alarm` | Traccar SOS alarm webhook |

---

## 8. Real-time Architecture: Firebase Realtime DB Structure

```json
{
  "live_locations": {
    "{child_id}": {
      "latest": {
        "lat": 18.5204,
        "lng": 73.8567,
        "battery": 82,
        "speed": 0,
        "is_moving": false,
        "device_id": "uuid-watch-1",
        "device_type": "watch",
        "updated_at": 1700000000
      },
      "devices": {
        "{device_id_watch}": {
          "lat": 18.5204,
          "lng": 73.8567,
          "battery": 82,
          "updated_at": 1700000000
        },
        "{device_id_bag}": {
          "lat": 18.5200,
          "lng": 73.8560,
          "battery": 45,
          "updated_at": 1699999800
        }
      }
    }
  },
  "sos": {
    "{child_id}": {
      "active": true,
      "lat": 18.5204,
      "lng": 73.8567,
      "triggered_at": 1700000000
    }
  },
  "alerts": {
    "{user_id}": {
      "{alert_id}": {
        "type": "geofence_exit",
        "child_name": "Aryan",
        "title": "Aryan left School",
        "timestamp": 1700000000
      }
    }
  }
}
```

---

## 9. Redis Cache Keys

```
location:child:{child_id}:latest          → {lat, lng, device_id, battery, ts}  TTL: 24h
location:device:{device_id}:latest        → {lat, lng, battery, ts}              TTL: 24h
geofence:{child_id}:{fence_id}:inside     → "true"/"false"                       TTL: 72h
device:{device_id}:online                 → "1"                                  TTL: 5min (sliding)
sos:{child_id}:active                     → "1"                                  TTL: until resolved
rate:otp:{phone}                          → count                                TTL: 1h
```

---

## 10. Monetization Tiers

| Feature | Free | Basic (₹99/AED 9 mo) | Premium (₹199/AED 19 mo) | School (Custom) |
|---|---|---|---|---|
| Children | 1 | 3 | Unlimited | 500+ |
| Devices/child | 1 | 2 | 3 | 2 |
| Location history | 24h | 7 days | 30 days | 90 days |
| Geofences | 1 | 5 | Unlimited | Unlimited |
| Family sharing | ❌ | 2 guardians | 5 guardians | Teachers |
| Sound around | ❌ | ✅ | ✅ | ✅ |
| Safe routes | ❌ | ❌ | ✅ | ✅ |
| School mode | ❌ | ✅ | ✅ | ✅ |
| Web dashboard | ❌ | ❌ | ❌ | ✅ |
| Attendance | ❌ | ❌ | ❌ | ✅ |
| Speed alerts | ❌ | ✅ | ✅ | ✅ |
| Weekly reports | ❌ | ❌ | ✅ | ✅ |

### India vs UAE Pricing Strategy
- India: INR 99/month Basic, INR 199/month Premium (~$1.15/$2.35)
- UAE: AED 9/month Basic, AED 19/month Premium (~$2.45/$5.17)
- Same features, market-adjusted pricing

### Hardware Bundle (India Launch Strategy)
- Watch + 3 months Premium = INR 2,499 (watch ₹1,800 + ₹699 app)
- Distributed via school tie-ups, Flipkart, Amazon

---

## 11. Tech Stack Summary

| Layer | Technology | Reason |
|---|---|---|
| Mobile App | Flutter 3.x | Single codebase iOS + Android |
| State Management | Riverpod | Null-safe, testable, less boilerplate |
| HTTP | Dio + Retrofit | Type-safe, interceptors, code-gen |
| Navigation | GoRouter | Declarative, deep-link support |
| Backend | FastAPI (Python) | Already used in FarryOn, async, fast |
| DB | PostgreSQL + partitioning | Location data volume, time-series queries |
| Cache | Redis | Sub-5ms live location reads |
| Realtime | Firebase Realtime DB | Flutter SDK, perfect for live map |
| GPS Middleware | Traccar | Device-agnostic, 170+ protocols, open-source |
| Push Notifications | FCM | Cross-platform, free, reliable |
| Auth | JWT + OTP (WhatsApp/SMS) | No email needed, India-friendly |
| Reverse Geocoding | Google Maps API | Address from lat/lng |
| Maps | Google Maps Flutter | Best India/UAE map data |
| Deployment | Docker + Docker Compose | Portable, dev → prod same config |
| CDN/Storage | Cloudflare R2 | Child photos, cheap bandwidth |

---

## 12. Development Timeline (Solo Builder)

| Phase | Duration | Deliverables |
|---|---|---|
| **Phase 1** | Weeks 1–3 | FastAPI backend, Traccar setup, PostgreSQL schema, Firebase RT DB wiring |
| **Phase 2** | Weeks 4–6 | Flutter app: Auth, Dashboard, Live Map, Single child+device |
| **Phase 3** | Weeks 7–8 | Multi-device support, Geofence UI + alerts, SOS flow |
| **Phase 4** | Weeks 9–10 | Location history, Family sharing/invite, Subscription paywall |
| **Beta** | Weeks 11–12 | 50-user beta with Wonlex watches in Pune/Sharjah schools |
| **Phase 5** | Weeks 13–16 | Sound around, Safe routes, School mode, Hindi/Arabic UI |
| **Launch** | Week 17 | Play Store + App Store + School partnership outreach |
| **Phase 6** | Weeks 18–22 | School dashboard (web), Attendance tracking, IzyLrn integration |

---

*Document prepared by Claude | IzySafe v1.0 Product Blueprint*
*Last updated: June 2026*
