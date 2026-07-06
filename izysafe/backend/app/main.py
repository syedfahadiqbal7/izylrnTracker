"""FastAPI application entrypoint.

Sprint 0 ships the app skeleton + /health (used by the docker healthcheck).
Feature routers (auth, children, devices, location, …) are mounted under
/api/v1 starting in Sprint 1.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.public_track import router as public_track_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.errors import register_exception_handlers
from app.core.firebase import init_firebase
from app.core.redis import close_redis, redis_client
from app.services.batch_writer import BatchWriter
from app.services.device_status import DeviceStatusMonitor
from app.services.fcm_gateway import FcmGateway

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("izysafe")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(
        "Starting IzySafe backend (env=%s, background_loops=%s)",
        settings.environment, settings.run_background_loops,
    )
    init_firebase()  # no-op + warning if creds absent (Sprint 2 wires it fully)
    app.state.batch_writer = app.state.status_monitor = None
    # The batch writer + status monitor are singletons — run only where enabled
    # (exactly one web instance) so extra replicas don't double-process.
    if settings.run_background_loops:
        batch_writer = BatchWriter(redis_client)
        batch_writer.start()  # 5s loop: drain batch:locations → bulk insert (Flow A)
        app.state.batch_writer = batch_writer
        status_monitor = DeviceStatusMonitor(redis_client, AsyncSessionLocal, FcmGateway())
        status_monitor.start()  # 60s loop: flip stale devices offline + alert
        app.state.status_monitor = status_monitor
    yield
    # Shutdown — stop the loops before closing Redis.
    if app.state.status_monitor is not None:
        await app.state.status_monitor.stop()
    if app.state.batch_writer is not None:
        await app.state.batch_writer.stop()
    await close_redis()
    logger.info("IzySafe backend stopped.")


# Hide interactive API docs in production (no schema disclosure).
_docs = None if settings.is_production else "/docs"
_redoc = None if settings.is_production else "/redoc"
_openapi = None if settings.is_production else "/openapi.json"

app = FastAPI(
    title="IzySafe API",
    version="0.1.0",
    description="GPS child-safety platform — India & UAE",
    lifespan=lifespan,
    docs_url=_docs,
    redoc_url=_redoc,
    openapi_url=_openapi,
)


@app.middleware("http")
async def security_headers(request, call_next):
    """Baseline security headers on every response (HSTS only in production)."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    if settings.is_production:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
        )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe for the docker healthcheck. Intentionally dependency-free
    so it passes before the DB migration has run."""
    return {"status": "ok"}


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"service": "izysafe-api", "version": "0.1.0", "docs": "/docs"}


# --- API v1 routers ----------------------------------------------------------
app.include_router(api_router, prefix="/api/v1")

# --- Public (login-less) live-tracking page, served at root: /track/{token} --
app.include_router(public_track_router)
