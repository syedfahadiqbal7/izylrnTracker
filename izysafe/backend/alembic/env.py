"""Alembic environment.

Runs migrations with a SYNC engine (psycopg2) derived from settings.sync_database_url,
while the application itself uses async (asyncpg). Importing app.models registers
every table on Base.metadata so autogenerate sees the full schema.
"""
from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make `app` importable (prepend_sys_path = . also covers this).
from app.core.config import settings  # noqa: E402
import app.models  # noqa: E402,F401  (side-effect: registers all tables)
from app.models.base import Base  # noqa: E402

config = context.config

# Inject the sync connection URL from our settings (single source of truth).
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a DB connection (alembic upgrade --sql)."""
    context.configure(
        url=settings.sync_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB using a sync engine."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
