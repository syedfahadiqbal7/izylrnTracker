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

    # ---- Auth / JWT ----
    jwt_secret: str = "change_me"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 1440
    jwt_refresh_expire_days: int = 30

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
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

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
