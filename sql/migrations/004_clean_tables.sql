-- ORBITWATCH – sql/migrations/004_clean_tables.sql
-- Phase 5: creates clean staging tables for all four datasets.
-- Idempotent: uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS.
-- Tables are in schema staging. etl_user gets full DML; dashboard_user gets NO access.
-- Applied with: python scripts/apply_sql.py sql/migrations/004_clean_tables.sql

-- ── gp_clean ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.gp_clean (
    norad_cat_id    TEXT,
    object_name     TEXT,
    object_id       TEXT,
    epoch           TIMESTAMPTZ,
    inclination     DOUBLE PRECISION,
    eccentricity    DOUBLE PRECISION,
    mean_motion     DOUBLE PRECISION,
    mean_anomaly    TEXT,
    arg_of_pericenter TEXT,
    ra_of_asc_node  TEXT,
    bstar           TEXT,
    mean_motion_dot TEXT,
    mean_motion_ddot TEXT,
    rev_at_epoch    TEXT,
    element_set_no  TEXT,
    ephemeris_type  TEXT,
    classification_type TEXT,
    source_group    TEXT,
    orbit_regime    TEXT,
    is_outlier      BOOLEAN,
    loaded_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gp_clean_norad ON staging.gp_clean (norad_cat_id);

-- ── k_index_clean ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.k_index_clean (
    time_tag        TIMESTAMPTZ,
    kp              TEXT,
    kp_index        DOUBLE PRECISION,
    estimated_kp    DOUBLE PRECISION,
    is_outlier      BOOLEAN,
    loaded_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_k_index_clean_tt ON staging.k_index_clean (time_tag);

-- ── solar_indices_clean ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.solar_indices_clean (
    time_tag        TEXT,
    f107            DOUBLE PRECISION,
    ssn             DOUBLE PRECISION,
    smoothed_ssn    DOUBLE PRECISION,
    smoothed_f107   DOUBLE PRECISION,
    observed_swpc_ssn DOUBLE PRECISION,
    smoothed_swpc_ssn DOUBLE PRECISION,
    is_outlier      BOOLEAN,
    loaded_at       TIMESTAMPTZ DEFAULT now()
);

-- ── satcat_clean ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS staging.satcat_clean (
    norad_cat_id    TEXT,
    object_name     TEXT,
    object_id       TEXT,
    object_type     TEXT,
    ops_status_code TEXT,
    owner           TEXT,
    launch_date     TIMESTAMPTZ,
    launch_site     TEXT,
    decay_date      TIMESTAMPTZ,
    period          DOUBLE PRECISION,
    inclination     DOUBLE PRECISION,
    apogee          DOUBLE PRECISION,
    perigee         DOUBLE PRECISION,
    rcs             TEXT,
    data_status_code TEXT,
    orbit_center    TEXT,
    orbit_type      TEXT,
    orbit_regime    TEXT,
    is_outlier      BOOLEAN,
    loaded_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_satcat_clean_norad ON staging.satcat_clean (norad_cat_id);

-- ── Grants: etl_user full DML; dashboard_user NO access to staging ───────────
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON staging.gp_clean          TO etl_user;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON staging.k_index_clean     TO etl_user;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON staging.solar_indices_clean TO etl_user;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON staging.satcat_clean       TO etl_user;
-- dashboard_user intentionally receives no GRANT on staging.* tables.
