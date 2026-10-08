-- ORBITWATCH – sql/init/02_schemas.sql
-- Creates the four application schemas and their tables.
-- Grants are applied following the principle of least privilege:
--   etl_user       → full DML on all four schemas
--   dashboard_user → SELECT on warehouse schema ONLY
--
-- This file is idempotent: CREATE IF NOT EXISTS is used throughout so it is
-- safe to re-inspect without dropping data.  (Postgres only runs initdb scripts
-- once on a fresh volume, but idempotency is good practice.)

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. SCHEMAS
-- ─────────────────────────────────────────────────────────────────────────────

-- staging  : raw data as loaded from sources, before cleaning.
CREATE SCHEMA IF NOT EXISTS staging;

-- warehouse: cleaned, modelled facts and dimensions for analysis.
CREATE SCHEMA IF NOT EXISTS warehouse;

-- audit    : pipeline run metadata, data lineage and access logs.
CREATE SCHEMA IF NOT EXISTS audit;

-- quality  : dead-letter queue for records that failed validation.
CREATE SCHEMA IF NOT EXISTS quality;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. AUDIT TABLES
-- ─────────────────────────────────────────────────────────────────────────────

-- audit.pipeline_runs
-- One row per pipeline execution; later phases write start/end times and stats.
CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
    run_id          UUID            PRIMARY KEY,
    pipeline_name   TEXT            NOT NULL,
    started_at      TIMESTAMPTZ     NOT NULL,
    finished_at     TIMESTAMPTZ,
    status          TEXT            NOT NULL,   -- e.g. 'running', 'success', 'failed'
    rows_in         BIGINT,
    rows_out        BIGINT,
    rows_rejected   BIGINT,
    notes           TEXT
);

-- audit.data_lineage
-- Tracks which source fed which target for every step in every run.
CREATE TABLE IF NOT EXISTS audit.data_lineage (
    lineage_id  BIGSERIAL       PRIMARY KEY,
    run_id      UUID            REFERENCES audit.pipeline_runs (run_id),
    source_name TEXT            NOT NULL,
    target_name TEXT            NOT NULL,
    step_name   TEXT            NOT NULL,
    row_count   BIGINT,
    recorded_at TIMESTAMPTZ     DEFAULT now()
);

-- audit.access_log
-- Lightweight access log; applications INSERT here after significant operations.
CREATE TABLE IF NOT EXISTS audit.access_log (
    log_id      BIGSERIAL       PRIMARY KEY,
    db_user     TEXT            NOT NULL,
    action      TEXT            NOT NULL,
    object_name TEXT,
    logged_at   TIMESTAMPTZ     DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. QUALITY TABLE
-- ─────────────────────────────────────────────────────────────────────────────

-- quality.dead_letter
-- Records that failed validation land here with a reason code so they can be
-- investigated and reprocessed without losing the original payload.
CREATE TABLE IF NOT EXISTS quality.dead_letter (
    dead_letter_id  BIGSERIAL   PRIMARY KEY,
    source_name     TEXT        NOT NULL,
    payload         JSONB       NOT NULL,
    reason_code     TEXT        NOT NULL,   -- short machine-readable code
    reason_detail   TEXT,                  -- human-readable explanation
    run_id          UUID,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. GRANTS – ETL USER
-- Principle: only the schemas and operations needed; nothing more.
-- ─────────────────────────────────────────────────────────────────────────────

-- Allow the ETL user to see and use all four schemas.
GRANT USAGE ON SCHEMA staging   TO etl_user;
GRANT USAGE ON SCHEMA warehouse TO etl_user;
GRANT USAGE ON SCHEMA audit     TO etl_user;
GRANT USAGE ON SCHEMA quality   TO etl_user;

-- Grant DML on all CURRENT tables.
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA staging   TO etl_user;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA warehouse TO etl_user;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA audit     TO etl_user;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA quality   TO etl_user;

-- Allow the ETL user to advance sequences (needed for BIGSERIAL columns).
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA staging   TO etl_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA warehouse TO etl_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA audit     TO etl_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA quality   TO etl_user;

-- ALTER DEFAULT PRIVILEGES: tables and sequences created in future phases
-- automatically get the same grants without needing to re-run this file.
ALTER DEFAULT PRIVILEGES IN SCHEMA staging
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO etl_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA warehouse
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO etl_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO etl_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA quality
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO etl_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA staging
    GRANT USAGE, SELECT ON SEQUENCES TO etl_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA warehouse
    GRANT USAGE, SELECT ON SEQUENCES TO etl_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit
    GRANT USAGE, SELECT ON SEQUENCES TO etl_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA quality
    GRANT USAGE, SELECT ON SEQUENCES TO etl_user;

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. GRANTS – DASHBOARD USER
-- Principle: read-only access to warehouse ONLY; no access to audit or quality.
-- ─────────────────────────────────────────────────────────────────────────────

GRANT USAGE ON SCHEMA warehouse TO dashboard_user;

GRANT SELECT ON ALL TABLES IN SCHEMA warehouse TO dashboard_user;

-- Ensure future tables in warehouse are also readable by the dashboard user.
ALTER DEFAULT PRIVILEGES IN SCHEMA warehouse
    GRANT SELECT ON TABLES TO dashboard_user;

-- Explicitly revoke any accidental privileges on other schemas.
REVOKE ALL ON SCHEMA staging FROM dashboard_user;
REVOKE ALL ON SCHEMA audit   FROM dashboard_user;
REVOKE ALL ON SCHEMA quality FROM dashboard_user;
