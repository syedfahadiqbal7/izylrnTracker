-- ============================================================================
-- Postgres initdb script — runs ONCE, only on first container init (empty volume)
-- ============================================================================
-- The main application database `izysafe` is created automatically by the
-- POSTGRES_DB env var. This script adds the SEPARATE database Traccar needs,
-- on the SAME PostgreSQL instance (critical requirement: Traccar must NOT use
-- its default H2 in-memory database).
--
-- Traccar manages its own schema via Liquibase on first start, so we only need
-- the empty database to exist. The IzySafe app schema (33 tables) is NOT loaded
-- here — it is applied by Alembic migrations in Sprint 0 / Step 6.
-- ============================================================================

CREATE DATABASE traccar;
GRANT ALL PRIVILEGES ON DATABASE traccar TO izysafe;
