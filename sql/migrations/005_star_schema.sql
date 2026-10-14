-- ORBITWATCH – sql/migrations/005_star_schema.sql
-- Phase 6: Dimensional Warehouse Schema (Star Schema in schema "dw")
-- Includes:
--   - Dimensions: dim_date, dim_orbit_regime, dim_object_type, dim_satellite (SCD Type 1)
--   - Facts: fact_gp_snapshot, fact_space_weather_month, fact_decay_month
--   - Primary keys, foreign keys, indexes on foreign keys
--   - Grants: etl_user full DML; dashboard_user SELECT on dw only
-- Applied with: python scripts/apply_sql.py sql/migrations/005_star_schema.sql

-- ── 1. Create Schema ─────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS dw;

-- ── 2. Dimension: dim_date ───────────────────────────────────────────────────
-- Generated calendar covering the data range (1749 to 2030).
-- Key format: YYYYMMDD integer. Month-level facts join on YYYYMM01.
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key        INT PRIMARY KEY,              -- e.g. 20261014 or 20261001
    calendar_date   DATE NOT NULL UNIQUE,
    year            SMALLINT NOT NULL,
    quarter         SMALLINT NOT NULL,
    month           SMALLINT NOT NULL,
    day             SMALLINT NOT NULL,
    day_of_week     SMALLINT NOT NULL,            -- 1 (Mon) to 7 (Sun)
    month_name      VARCHAR(20) NOT NULL,
    is_month_start  BOOLEAN NOT NULL
);

-- Seed dim_date calendar
INSERT INTO dw.dim_date (
    date_key, calendar_date, year, quarter, month, day, day_of_week, month_name, is_month_start
)
SELECT
    (EXTRACT(YEAR FROM d)::INT * 10000 + EXTRACT(MONTH FROM d)::INT * 100 + EXTRACT(DAY FROM d)::INT) AS date_key,
    d::DATE AS calendar_date,
    EXTRACT(YEAR FROM d)::SMALLINT AS year,
    EXTRACT(QUARTER FROM d)::SMALLINT AS quarter,
    EXTRACT(MONTH FROM d)::SMALLINT AS month,
    EXTRACT(DAY FROM d)::SMALLINT AS day,
    EXTRACT(ISODOW FROM d)::SMALLINT AS day_of_week,
    TRIM(TO_CHAR(d, 'Month')) AS month_name,
    (EXTRACT(DAY FROM d) = 1) AS is_month_start
FROM generate_series('1749-01-01'::date, '2030-12-31'::date, '1 day'::interval) AS d
ON CONFLICT (date_key) DO NOTHING;

-- ── 3. Dimension: dim_orbit_regime ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.dim_orbit_regime (
    regime_id       SERIAL PRIMARY KEY,
    regime_code     VARCHAR(20) NOT NULL UNIQUE,
    regime_name     VARCHAR(50) NOT NULL,
    description     TEXT
);

INSERT INTO dw.dim_orbit_regime (regime_code, regime_name, description) VALUES
    ('LEO',     'Low Earth Orbit',           'Altitude below 2,000 km'),
    ('MEO',     'Medium Earth Orbit',        'Altitude between 2,000 km and 35,500 km'),
    ('GEO',     'Geostationary Orbit',       'Circular orbit at ~35,786 km (35,500 - 36,000 km)'),
    ('HEO',     'High / Highly Elliptical',  'Apogee exceeding 36,000 km'),
    ('UNKNOWN', 'Unclassified Orbit',        'Missing or unclassifiable orbital parameters')
ON CONFLICT (regime_code) DO NOTHING;

-- ── 4. Dimension: dim_object_type ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dw.dim_object_type (
    object_type_id      SERIAL PRIMARY KEY,
    object_type_code    VARCHAR(20) NOT NULL UNIQUE,
    object_type_name    VARCHAR(50) NOT NULL,
    description         TEXT
);

INSERT INTO dw.dim_object_type (object_type_code, object_type_name, description) VALUES
    ('PAY', 'Payload',      'Operational or decommissioned satellite payload'),
    ('R/B', 'Rocket Body',  'Spent launch vehicle upper stage or booster'),
    ('DEB', 'Debris',       'Fragmentation, mission-related, or collision debris'),
    ('UNK', 'Unknown',      'Unidentified trackable orbital object')
ON CONFLICT (object_type_code) DO NOTHING;

-- ── 5. Dimension: dim_satellite ──────────────────────────────────────────────
-- SCD Type 1: Satellite attributes are overwritten on load to reflect current catalog state.
CREATE TABLE IF NOT EXISTS dw.dim_satellite (
    satellite_key       SERIAL PRIMARY KEY,      -- Surrogate key
    norad_cat_id        TEXT NOT NULL UNIQUE,     -- Natural key
    object_name         TEXT,
    object_id           TEXT,
    object_type_id      INT REFERENCES dw.dim_object_type(object_type_id),
    ops_status_code     TEXT,
    owner               TEXT,
    launch_date         TIMESTAMPTZ,
    launch_site         TEXT,
    decay_date          TIMESTAMPTZ,
    period              DOUBLE PRECISION,
    inclination         DOUBLE PRECISION,
    apogee              DOUBLE PRECISION,
    perigee             DOUBLE PRECISION,
    rcs                 TEXT,
    data_status_code    TEXT,
    orbit_center        TEXT,
    orbit_type          TEXT,
    orbit_regime_id     INT REFERENCES dw.dim_orbit_regime(regime_id),
    is_outlier          BOOLEAN,
    loaded_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dim_sat_norad  ON dw.dim_satellite (norad_cat_id);
CREATE INDEX IF NOT EXISTS idx_dim_sat_type   ON dw.dim_satellite (object_type_id);
CREATE INDEX IF NOT EXISTS idx_dim_sat_regime ON dw.dim_satellite (orbit_regime_id);

-- ── 6. Fact: fact_gp_snapshot ────────────────────────────────────────────────
-- Grain: One row per satellite per epoch snapshot observation.
CREATE TABLE IF NOT EXISTS dw.fact_gp_snapshot (
    snapshot_id         BIGSERIAL PRIMARY KEY,
    satellite_key       INT NOT NULL REFERENCES dw.dim_satellite(satellite_key),
    date_key            INT NOT NULL REFERENCES dw.dim_date(date_key),
    epoch               TIMESTAMPTZ NOT NULL,
    orbit_regime_id     INT NOT NULL REFERENCES dw.dim_orbit_regime(regime_id),
    inclination         DOUBLE PRECISION,
    eccentricity        DOUBLE PRECISION,
    mean_motion         DOUBLE PRECISION,
    bstar               DOUBLE PRECISION,
    is_outlier          BOOLEAN,
    loaded_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fact_gp_sat    ON dw.fact_gp_snapshot (satellite_key);
CREATE INDEX IF NOT EXISTS idx_fact_gp_date   ON dw.fact_gp_snapshot (date_key);
CREATE INDEX IF NOT EXISTS idx_fact_gp_regime ON dw.fact_gp_snapshot (orbit_regime_id);

-- ── 7. Fact: fact_space_weather_month ────────────────────────────────────────
-- Grain: One row per calendar month.
CREATE TABLE IF NOT EXISTS dw.fact_space_weather_month (
    weather_month_id    SERIAL PRIMARY KEY,
    date_key            INT NOT NULL REFERENCES dw.dim_date(date_key),  -- YYYYMM01
    f107                DOUBLE PRECISION,
    ssn                 DOUBLE PRECISION,
    smoothed_f107       DOUBLE PRECISION,
    smoothed_ssn        DOUBLE PRECISION,
    loaded_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fact_sw_date   ON dw.fact_space_weather_month (date_key);

-- ── 8. Fact: fact_decay_month ────────────────────────────────────────────────
-- Grain: One row per calendar month and orbit regime.
-- Aggregates objects from satcat_clean having non-null DECAY_DATE in that month.
CREATE TABLE IF NOT EXISTS dw.fact_decay_month (
    decay_month_id      SERIAL PRIMARY KEY,
    date_key            INT NOT NULL REFERENCES dw.dim_date(date_key),  -- YYYYMM01
    orbit_regime_id     INT NOT NULL REFERENCES dw.dim_orbit_regime(regime_id),
    decay_count         INT NOT NULL,
    loaded_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fact_decay_date   ON dw.fact_decay_month (date_key);
CREATE INDEX IF NOT EXISTS idx_fact_decay_regime ON dw.fact_decay_month (orbit_regime_id);

-- ── 9. Permissions / Grants ──────────────────────────────────────────────────
-- etl_user receives full DML on dw schema and all tables/sequences.
GRANT USAGE ON SCHEMA dw TO etl_user, dashboard_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA dw TO etl_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA dw TO etl_user;

-- dashboard_user receives SELECT only on dw tables.
GRANT SELECT ON ALL TABLES IN SCHEMA dw TO dashboard_user;

-- Ensure future tables inherit the same permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA dw GRANT ALL PRIVILEGES ON TABLES TO etl_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA dw GRANT SELECT ON TABLES TO dashboard_user;
