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

from app.core.config import settings
from app.core.firebase import init_firebase
from app.core.redis import close_redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("izysafe")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting IzySafe backend (env=%s)", settings.environment)
    init_firebase()  # no-op + warning if creds absent (Sprint 2 wires it fully)
    yield
    # Shutdown
    await close_redis()
    logger.info("IzySafe backend stopped.")


app = FastAPI(
    title="IzySafe API",
    version="0.1.0",
    description="GPS child-safety platform — India & UAE",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Liveness probe for the docker healthcheck. Intentionally dependency-free
    so it passes before the DB migration has run."""
    return {"status": "ok"}


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"service": "izysafe-api", "version": "0.1.0", "docs": "/docs"}


# --- API v1 routers (mounted from Sprint 1 onward) ---------------------------
# from app.api.v1.router import api_router
# app.include_router(api_router, prefix="/api/v1")
