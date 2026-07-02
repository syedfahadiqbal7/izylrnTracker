"""Application configuration — Pydantic v2 settings loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Environment ----
    environment: str = "development"

    # ---- PostgreSQL ----
    # Async URL (asyncpg) used by the app. Alembic derives a sync URL from this.
    database_url: str = "postgresql+asyncpg://izysafe:change_me_dev_password@localhost:5432/izysafe"

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"

    # ---- Firebase (Sprint 2) ----
    firebase_credentials_json: str = "/app/secrets/firebase-service-account.json"
    firebase_database_url: str = ""

    # ---- Traccar ----
    traccar_url: str = "http://traccar:8082"
    traccar_api_user: str = ""
    traccar_api_password: str = ""
    traccar_webhook_secret: str = "change_me_webhook_secret"

    # ---- Device status (Sprint 2) ----
    device_offline_threshold_seconds: int = 900   # 15 min without a position → offline
    device_sweep_interval_seconds: int = 60       # offline-detection sweep cadence

    # ---- Battery alerts (Sprint 2) ----
    battery_critical_threshold: int = 5           # ≤5% → critical_battery (low = per-device)
    battery_alert_cooldown_seconds: int = 14400   # 4h debounce per device + level

    # ---- Speed alerts (Sprint 2) ----
    speed_window_seconds: int = 90                # sliding window for sustained samples
    speed_required_samples: int = 3              # over-threshold samples before firing
    speed_alert_cooldown_seconds: int = 600       # 10 min debounce per child

    # ---- Geofences (Sprint 3) ----
    geofence_debounce_seconds: int = 300          # 5 min anti-jitter debounce per child+fence

    # ---- Safe Routes (Sprint 7, F20) ----
    route_debounce_seconds: int = 300             # 5 min anti-jitter debounce per child+route

    # ---- Pickup detection (Sprint 7, F17) ----
    pickup_window_before_min: int = 30            # window opens this long before school_hours_to
    pickup_window_after_min: int = 90             # window closes this long after school_hours_to
    pickup_vehicle_speed_kmh: float = 10.0        # ≥ → in_vehicle, < → on_foot

    # ---- Share Links (Sprint 7, F22) ----
    share_link_default_ttl_hours: int = 1         # default validity when caller omits ttl_hours
    share_link_base_url: str = "https://izysafe.app/track"  # public track-page base ({base}/{token})
    share_view_rate_per_min: int = 60             # public GET /share/{token} views per IP per minute

    # ---- Audio: Sound Around (F11) / Two-way Call (F12) — Sprint 5 ----
    # Outbound Traccar SIM-command templates (CLAUDE.md §3.12, docs/HARDWARE_SPIKE.md §4).
    # The exact string is GT06-model-specific and UNVALIDATED on hardware — kept in config
    # so ops can swap it per watch model without a code change. {phone} is the number the
    # watch dials back (the requesting parent/guardian).
    traccar_monitor_template: str = "MONITOR,{phone}#"    # Sound Around: silent ambient listen
    traccar_callback_template: str = "CALLBACK,{phone}#"  # Two-way Call: duplex (Slice 2)
    sound_around_daily_limit: int = 3                     # Sound Around sessions per child per day
    # No hang-up signal exists (audio is off-server), so a Two-way Call is considered
    # "in progress" for this bounded window to block concurrent re-dials.
    two_way_call_active_seconds: int = 300                # 5 min in-progress guard per child

    # ---- Scheduled jobs / Celery (Sprint 6) ----
    celery_broker_url: str = ""                   # falls back to redis_url when empty
    celery_result_backend: str = ""               # falls back to redis_url when empty
    soft_delete_retention_days: int = 30          # purge users/children/devices deleted before this
    partition_lookahead_months: int = 3           # months of locations partitions to keep ahead

    # ---- Auth / JWT ----
    jwt_secret: str = "change_me"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 1440
    jwt_refresh_expire_days: int = 30

    # ---- School / B2B (Sprint 8) ----
    school_seed_secret: str = ""              # env-gated bootstrap secret; empty ⇒ seed disabled
    school_login_max_attempts: int = 10       # failed logins per email per window
    school_login_window_seconds: int = 900    # 15 min brute-force window

    # ---- Bus tracking (Sprint 8, F28) ----
    bus_stop_radius_m: int = 150              # within this of a stop ⇒ "arrived" (bus_arrival)
    bus_stop_debounce_seconds: int = 300      # 5 min anti-repeat per route+stop
    bus_avg_speed_kmh: float = 20.0           # for the straight-line ETA estimate

    # ---- Email / SMTP (Sprint 9) ----
    smtp_host: str = ""                       # empty ⇒ EmailGateway no-ops (logs a warning)
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@izysafe.app"
    smtp_use_tls: bool = True

    # ---- School-admin password reset (Sprint 9) ----
    pwreset_token_ttl_minutes: int = 30
    pwreset_base_url: str = "https://izysafe.app/school/reset-password"
    pwreset_rate_per_email: int = 3           # forgot-password requests per email per window
    pwreset_rate_per_ip: int = 10             # per IP per window
    pwreset_rate_window_seconds: int = 3600   # 1 hour

    # ---- School-admin self-service password change (Sprint 9 Slice 2) ----
    pwchange_max_attempts: int = 5            # change-password attempts per admin per window
    pwchange_window_seconds: int = 900        # 15 min

    # ---- OTP (Sprint 1) ----
    msg91_auth_key: str = ""
    msg91_whatsapp_template: str = ""   # MSG91 WhatsApp template/flow id
    twilio_sid: str = ""
    twilio_token: str = ""
    twilio_from_number: str = ""

    # OTP behaviour
    otp_length: int = 6
    otp_expiry_minutes: int = 10
    otp_max_attempts: int = 3
    whatsapp_fallback_seconds: int = 30   # wait before falling back to SMS

    # Rate limits (Redis counters)
    otp_rate_per_phone: int = 5           # per window
    otp_rate_per_ip: int = 20             # per window
    otp_rate_window_seconds: int = 3600   # 1 hour

    # ---- Payments (Sprint 6) ----
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""     # HMAC-SHA256 secret for /webhook/razorpay
    razorpay_plan_basic: str = ""         # Razorpay recurring Plan ID (dashboard) — Basic
    razorpay_plan_premium: str = ""       # Razorpay recurring Plan ID — Premium
    subscription_total_count: int = 12    # billing cycles before a subscription completes
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""       # signing secret for /webhook/stripe
    stripe_price_basic: str = ""          # Stripe recurring Price ID — Basic
    stripe_price_premium: str = ""        # Stripe recurring Price ID — Premium
    payment_success_url: str = "https://izysafe.app/pay/success"  # Stripe hosted-checkout return
    payment_cancel_url: str = "https://izysafe.app/pay/cancel"

    # ---- Storage: Cloudflare R2 ----
    r2_access_key: str = ""
    r2_secret_key: str = ""
    r2_bucket: str = "izysafe-dev"
    r2_endpoint: str = ""

    # ---- Google Maps ----
    google_maps_api_key: str = ""

    # ---- App ----
    backend_url: str = "http://localhost:8000"
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"
    invite_base_url: str = "https://izysafe.app/invite"   # guardian invite deep link base
    invite_expiry_hours: int = 48

    # ------------------------------------------------------------------ helpers
    @property
    def sync_database_url(self) -> str:
        """Sync URL for Alembic migrations (psycopg2). The app itself stays async."""
        return self.database_url.replace("+asyncpg", "+psycopg2")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton — import this everywhere instead of instantiating Settings."""
    return Settings()


settings = get_settings()
