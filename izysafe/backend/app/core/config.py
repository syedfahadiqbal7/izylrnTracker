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

    # ---- Auth / JWT ----
    jwt_secret: str = "change_me"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 1440
    jwt_refresh_expire_days: int = 30

    # ---- OTP (Sprint 1) ----
    msg91_auth_key: str = ""
    twilio_sid: str = ""
    twilio_token: str = ""
    twilio_from_number: str = ""

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
