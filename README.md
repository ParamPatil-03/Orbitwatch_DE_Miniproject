# ORBITWATCH: Space Domain Awareness & Atmospheric Drag Data Platform

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![MongoDB 7](https://img.shields.io/badge/MongoDB-7.0-47A248.svg)](https://www.mongodb.com/)
[![Redpanda](https://img.shields.io/badge/Redpanda-Kafka_Compatible-FF4B4B.svg)](https://redpanda.com/)
[![Prefect](https://img.shields.io/badge/Prefect-3.8-024DFD.svg)](https://www.prefect.io/)
[![Delta Lake](https://img.shields.io/badge/Delta_Lake-1.6-00ADD8.svg)](https://delta.io/)
[![DuckDB](https://img.shields.io/badge/DuckDB-1.5-FFF000.svg)](https://duckdb.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.65-FF4B4B.svg)](https://streamlit.io/)
[![Tests](https://img.shields.io/badge/pytest-43_passed-brightgreen.svg)](tests/)

**ORBITWATCH** is an end-to-end, enterprise-grade Space Domain Awareness (SDA) and Space Weather Telemetry Data Platform. It ingests, streams, cleans, validates, models, and serves orbital ephemerides from **CelesTrak** alongside historical geomagnetic and solar indices from the **NOAA Space Weather Prediction Center (SWPC)**.

The platform provides a complete data engineering solution: from polyglot raw ingestion (MongoDB) and event-driven change-data capture streaming (Redpanda) to automated data quality gates (Great Expectations), a Kimball-style dimensional star schema (PostgreSQL `dw`), an ACID Lakehouse export (Delta Lake + DuckDB), workflow orchestration (Prefect), and an executive analytical dashboard (Streamlit).

---

## Table of Contents

1. [Quick Start & Installation (One-Click Launcher)](#quick-start--installation-for-new-clones)
2. [Live Demonstration Guide (The 4 Interactive Interfaces)](#live-demonstration-guide-the-4-interactive-interfaces)
3. [High-Level Architecture](#high-level-architecture)
3. [Dimensional Star Schema (Schema `dw`)](#dimensional-star-schema-schema-dw)
4. [Project Directory Layout](#project-directory-layout)
5. [Infrastructure & Services](#infrastructure--services)
6. [Phase-by-Phase Technical Breakdown](#phase-by-phase-technical-breakdown)
   - [Phase 1: Infrastructure & Security](#phase-1-infrastructure--security)
   - [Phase 2: Exploratory Data Analysis & Cleaning](#phase-2-exploratory-data-analysis--cleaning)
   - [Phase 3: FastAPI Ingestion Microservice](#phase-3-fastapi-ingestion-microservice)
   - [Phase 4: Event-Driven Streaming Pipeline](#phase-4-event-driven-streaming-pipeline)
   - [Phase 5: Data Quality Gates (Great Expectations)](#phase-5-data-quality-gates-great-expectations)
   - [Phase 6: Dimensional Warehouse (Schema `dw`)](#phase-6-dimensional-warehouse-schema-dw)
   - [Phase 7: Workflow Orchestration (Prefect Flow)](#phase-7-workflow-orchestration-prefect-flow)
   - [Phase 8: Lakehouse Layer (Delta Lake + DuckDB)](#phase-8-lakehouse-layer-delta-lake--duckdb)
   - [Phase 9: Operational Intelligence Dashboard (Streamlit)](#phase-9-operational-intelligence-dashboard-streamlit)
   - [Phase 10: Verification & System Testing](#phase-10-verification--system-testing)
7. [Step-by-Step Manual Execution Guide](#step-by-step-manual-execution-guide)
8. [Auditing, Data Lineage & Dead-Letter Verification](#auditing-data-lineage--dead-letter-verification)
9. [Physical Insights: Solar Flux vs. Orbital Decay](#physical-insights-solar-flux-vs-orbital-decay)
10. [Known Limitations & Technical Trade-Offs](#known-limitations--technical-trade-offs)
11. [Viva Examination Defense Highlights](#viva-examination-defense-highlights)

---

## Quick Start & Installation (For New Clones)

### Prerequisites (Only 2 Requirements)
Before running this project on any machine, ensure you have:
1. **Python 3.11 or higher** ([python.org](https://www.python.org/downloads/)) — *(Ensure **"Add python.exe to PATH"** is checked during installation)*.
2. **Docker Desktop** ([docker.com](https://www.docker.com/products/docker-desktop/)) — *(Must be running in the background)*.

---

### Running on Any Computer (Zero-Config 2-Step Run)

If you or anyone else just cloned/downloaded this repository onto a fresh computer:

1. **Open Docker Desktop** (ensure the engine is running).
2. **Double-click [`start_orbitwatch.bat`](start_orbitwatch.bat)** (or run `.\start_orbitwatch.bat` from Command Prompt / PowerShell).

#### What `start_orbitwatch.bat` does automatically on first run:
- **Automatic Configuration:** Detects if `.env` is missing and copies `.env.example` $\rightarrow$ `.env`.
- **Automatic Virtual Environment:** Detects if `.venv` is missing, creates it, and installs all required dependencies from `requirements.txt`.
- **Container Orchestration:** Boots up PostgreSQL 16, MongoDB 7, and Redpanda via `docker compose up -d`.
- **Database Migrations:** Applies SQL migrations (`001` to `005`) for staging, audit, quality, and dimensional star schema (`dw`).
- **Initial Data Pipeline:** If the database is empty, it runs initial ingestion, validation, and warehouse loading.
- **Launches Demonstration Environment:** Automatically opens all 4 interactive presentation tabs in your browser (**Streamlit**, **Redpanda Console**, **FastAPI Swagger Docs**, and **Great Expectations Quality Report**).

---

## Live Demonstration Guide (The 4 Interactive Interfaces)

When you run `start_orbitwatch.bat`, the system boots up and automatically opens 4 interconnected browser tabs to showcase every layer of the platform:

| Tab | Service | URL / Location | Purpose in the Architecture |
| :---: | :--- | :--- | :--- |
| **1** | **Streamlit Executive Dashboard** | `http://localhost:8501` | **Serving & Analytics Layer:** Visualizes space domain metrics, orbital regime distributions (LEO, MEO, GEO), and the physical correlation ($r \approx 0.706$) between Solar Radio Flux ($F_{10.7}$) and Satellite Atmospheric Decays. Runs as read-only `dashboard_user`. |
| **2** | **Redpanda Console** | `http://localhost:8080` | **Event Streaming Layer (Kafka):** Visualizes live streaming topics (`orbitwatch.gp_updates`, `orbitwatch.solar_updates`), consumer group offsets, partition throughput, and real-time JSON message envelopes. |
| **3** | **FastAPI Ingestion Docs** | `http://localhost:8000/docs#/` | **REST Microservice Layer:** Interactive Swagger UI for authenticated telemetry ingestion (`X-API-Key`). Validates incoming payloads via Pydantic schemas and enforces idempotency before writing to MongoDB 7. |
| **4** | **Great Expectations Data Docs** | `docs/validation_report/index.html` | **Automated Data Quality Layer:** Standalone HTML testing portal showing the pass/fail results for 8 expectation suites (bounds checks on inclination $0^\circ \le i \le 180^\circ$, eccentricity $0 \le e < 1$, chronological integrity, and dead-letter quarantine). |

---

### Step-by-Step Live Data Journey (How to Demonstrate Changes Across All 4 Systems)

Follow these 4 steps in front of your teacher/evaluator to prove that data flows live from ingestion to streaming, quality testing, and executive dashboarding:

```
[ Step 1: FastAPI ] ──▶ [ Step 2: Redpanda ] ──▶ [ Step 3: Great Expectations ] ──▶ [ Step 4: Streamlit ]
   POST New Satellite      Message Streamed Live       Automated Quality Gate Passes    Dashboard KPI Increments
```

#### Step 1: Ingest a New Satellite on FastAPI (`http://localhost:8000/docs#/`)
1. Open `http://localhost:8000/docs#/` in your browser.
2. Click the green **Authorize** button (top right 🔒).
3. In the `Value:` field, enter:
   ```text
   change_me_api_key
   ```
   *(Click "Authorize", then "Close")*.
4. Click on **`POST /ingest/{source}`** $\rightarrow$ click **`Try it out`**.
5. Set:
   * **`source`**: `satcat`
   * **`Request body`**: Paste this JSON payload:
     ```json
     {
       "NORAD_CAT_ID": 99999,
       "OBJECT_NAME": "PROJECT-ORBITWATCH",
       "OBJECT_TYPE": "PAY",
       "OWNER": "IND",
       "LAUNCH_DATE": "2026-10-15"
     }
     ```
6. Click the blue **Execute** button.
   * **Visible Result on Screen 1:** You get `HTTP 200` with `"inserted": 1` and a unique `batch_id`. The satellite is now stored in MongoDB!

#### Step 2: Stream Live to Redpanda Kafka Broker (`http://localhost:8080/`)
1. Open a PowerShell terminal in the project directory:
   ```powershell
   cd "c:\Users\PARAM\Desktop\de miniproject\orbitwatch"
   .venv\Scripts\python.exe src/orbitwatch/streaming/producer.py --source gp --limit 5
   ```
2. Open **Redpanda Console** (`http://localhost:8080`).
3. Click **Topics** $\rightarrow$ select **`orbitwatch.gp_updates`** $\rightarrow$ click the **Messages** tab.
   * **Visible Result on Screen 2:** The total message count ticks up by **+5**. Click the top message to inspect the deterministic `event_id` (UUIDv5) and real-time UTC timestamp!

#### Step 3: Run Automated Great Expectations Validation (`docs/validation_report/index.html`)
1. In your PowerShell terminal, execute the quality gates:
   ```powershell
   .venv\Scripts\python.exe scripts/run_validation.py --dataset satcat
   ```
2. Open `docs/validation_report/index.html` in your browser and press **`F5` (Refresh)**.
   * **Visible Result on Screen 3:** A brand-new validation run appears at the top of the **Validation Results** table with the exact current timestamp and a green checkmark (`Success`), proving automated testing verified all columns.

#### Step 4: Load into Warehouse and View on Streamlit Dashboard (`http://localhost:8501/`)
1. In your PowerShell terminal, execute the dimensional warehouse load:
   ```powershell
   .venv\Scripts\python.exe scripts/load_warehouse.py
   ```
2. Go to **Streamlit** (`http://localhost:8501/`) and press **`R`** (or refresh the page).
   * **Visible Result on Screen 4:** The first KPI card **"Catalogued Satellites"** increments live (e.g., from `70,953` to `70,954`)!

---

## High-Level Architecture

```text
===================================================================================
                               1. INGESTION LAYER
   +-----------------------+                    +------------------------+
   |   CelesTrak Telemetry |                    |   NOAA SWPC Telemetry  |
   |  (SATCAT, GP Orbits)  |                    |  (F10.7, SSN, K-Index) |
   +-----------+-----------+                    +-----------+------------+
               |                                            |
               +--------------------->+<--------------------+
                                      |
                          [FastAPI Ingestion :8000]
                                      |
                                      v
                      [(MongoDB 7 Raw Document Store)]
======================================+============================================
                                      |
                                      v
======================================+============================================
                         2. EVENT STREAMING LAYER
                 [Kafka Producer (MongoDB CDC Events)]
                                      |
                                      v
                 [Redpanda Broker :19092] <====> [Redpanda Console UI :8080]
                                      |
                                      v
                 [Kafka Consumer (Validation & Envelope Parsing)]
======================================+============================================
                                      |
                                      v
======================================+============================================
                     3. STAGING & QUALITY LAYER (PostgreSQL)
                 [(staging.*_raw Database Tables)]
                                      |
                                      v
                 [Great Expectations 1.x Quality Gates]
                     /                           \
           (Valid Records)                    (Quarantined)
                 v                                 v
   [(staging.*_clean Tables)]        [(quality.dead_letter / CSVs)]
                 |
                 +======> [audit.pipeline_runs & audit.data_lineage]
======================================+============================================
                                      |
                                      v
======================================+============================================
                   4. DIMENSIONAL STAR SCHEMA (PostgreSQL dw)
                 [Warehouse Loader (Atomic Truncate-and-Load)]
                                      |
                                      v
   DIMENSIONS: dim_date | dim_satellite | dim_orbit_regime | dim_object_type
   FACTS:      fact_gp_snapshot | fact_space_weather_month | fact_decay_month
======================================+============================================
                                      |
                +---------------------+---------------------+
                |                                           |
                v                                           v
====================================+   ============================================
        5. LAKEHOUSE LAYER          |              6. SERVING & DASHBOARD
   [Delta Lake Parquet Export]      |     [Streamlit Executive Dashboard :8501]
                |                   |     - Authenticated as 'dashboard_user'
                v                   |     - Summary KPIs & Regime Distribution
   [(data/lake/ Delta Tables)]      |     - Solar Flux vs Decays Chart (r = 0.706)
                |                   |     - Latest GP Orbital Mechanics Table
                v                   |   ============================================
   [DuckDB Vectorized Query Engine] |
====================================+
```

---

## Dimensional Star Schema (Schema `dw`)

The analytics warehouse is organized as a Kimball-style dimensional star schema under schema `dw`:

### Fact Tables

| Fact Table | Grain (1 row per...) | Primary Key | Foreign Keys | Metrics / Measures |
| :--- | :--- | :--- | :--- | :--- |
| **`dw.fact_gp_snapshot`** | Satellite per epoch snapshot | `snapshot_id` | `satellite_key` $\rightarrow$ `dim_satellite`<br>`date_key` $\rightarrow$ `dim_date`<br>`orbit_regime_id` $\rightarrow$ `dim_orbit_regime` | `mean_motion`, `eccentricity`, `inclination`, `bstar`, `is_outlier` |
| **`dw.fact_space_weather_month`** | Calendar month (1st of month) | `weather_month_id` | `date_key` $\rightarrow$ `dim_date` | `f107` (observed 10.7cm solar radio flux), `ssn` (sunspot number), `smoothed_f107`, `smoothed_ssn` |
| **`dw.fact_decay_month`** | Month per orbit regime | `decay_month_id` | `date_key` $\rightarrow$ `dim_date`<br>`orbit_regime_id` $\rightarrow$ `dim_orbit_regime` | `decay_count` (total satellites/debris re-entering Earth's atmosphere) |

### Dimension Tables

| Dimension Table | Key Type | Primary Key | Natural Key / Codes | Attributes |
| :--- | :--- | :--- | :--- | :--- |
| **`dw.dim_satellite`** | Surrogate (SCD Type 1) | `satellite_key` | `norad_cat_id` | `object_name`, `object_id`, `owner`, `launch_date`, `decay_date`, `period`, `inclination`, `apogee`, `perigee`, `rcs` |
| **`dw.dim_date`** | Integer Calendar Key | `date_key` (`YYYYMMDD`) | `calendar_date` | `year`, `quarter`, `month`, `day`, `day_of_week`, `month_name`, `is_month_start` (102,998 days: 1749 to 2030) |
| **`dw.dim_orbit_regime`** | Conformed Reference | `regime_id` | `regime_code` | `LEO` (Low Earth Orbit), `MEO` (Medium), `GEO` (Geostationary), `HEO` (High/Elliptical), `UNKNOWN` |
| **`dw.dim_object_type`** | Conformed Reference | `object_type_id` | `object_type_code` | `PAY` (Payload/Satellite), `R/B` (Rocket Body), `DEB` (Debris), `UNK` (Unknown) |

---

## Project Directory Layout

```text
orbitwatch/
├── .env.example                     # Reference environment configuration
├── .gitignore                       # Git exclusion rules (ignores raw data, lake, logs)
├── README.md                        # Master project documentation
├── pyproject.toml                   # Project metadata & pytest configuration
├── requirements.txt                 # Pinned Python package dependencies
├── start_orbitwatch.bat             # Single all-in-one Windows launcher
├── app/
│   └── dashboard.py                 # Streamlit Executive Dashboard (Phase 9)
├── config/
│   ├── __init__.py
│   └── settings.py                  # Pydantic v2 Settings & environment resolution
├── data/
│   ├── curated/                     # Cleaned flat parquet/csv outputs
│   ├── errors/                      # Quarantined CSV records from Phase 2
│   ├── lake/                        # Delta Lake ACID tables (fact_*, dim_satellite)
│   ├── raw/                         # Raw downloaded CelesTrak & NOAA SWPC samples
│   └── staging/                     # Staging artifacts
├── docs/
│   ├── data_profile.md              # Phase 2 exploratory data profiling report
│   ├── normalization.md             # Phase 6 1NF -> 3NF analysis & star schema rationale
│   ├── viva_notes.md                # Technical oral viva notes & question bank
│   ├── figures/                     # EDA visual distribution plots
│   └── validation_report/           # Compiled standalone Great Expectations HTML report
├── flows/
│   └── orbitwatch_flow.py           # Prefect orchestration flow with retries & failure stops
├── gx/                              # Great Expectations 1.x configuration & store
├── scripts/
│   ├── apply_sql.py                 # Idempotent SQL migration runner
│   ├── create_topics.py             # Redpanda topic creator
│   ├── export_lakehouse.py          # Delta Lake export script
│   ├── healthcheck.py               # Multi-service infrastructure connectivity check
│   ├── load_raw_to_mongo.py         # Bulk loader from data/raw/ to MongoDB
│   ├── load_warehouse.py            # Truncate-and-load dimensional ETL
│   ├── query_lake.py                # DuckDB analytical queries over Delta tables
│   ├── run_phase2.py                # Exploratory data profiling & baseline cleaning
│   └── run_validation.py            # Great Expectations validation runner
├── sql/
│   ├── init.sql                     # PostgreSQL initialization (users, roles, schemas)
│   └── migrations/
│       ├── 001_initial_schema.sql   # Core tables & role permissions
│       ├── 002_audit_tables.sql     # audit.pipeline_runs & audit.data_lineage
│       ├── 003_staging_tables.sql   # staging.*_raw & quality.dead_letter
│       ├── 004_clean_tables.sql     # staging.*_clean tables
│       └── 005_star_schema.sql      # dw.* dimensional star schema
├── src/
│   └── orbitwatch/
│       ├── common/
│       │   ├── db.py                # SQLAlchemy engine factories (etl & dashboard roles)
│       │   └── logging_setup.py     # Centralized structured logging
│       ├── etl/
│       │   ├── cleaning.py          # Domain cleaning logic & outlier flagging
│       │   └── suites.py            # Great Expectations expectations suites (Raw & Clean)
│       ├── ingestion/
│       │   ├── api.py               # FastAPI microservice for raw payload ingestion
│       │   └── download_samples.py  # HTTP scraper for CelesTrak and NOAA SWPC
│       └── streaming/
│           ├── producer.py          # MongoDB Change Data Capture streaming to Kafka
│           └── consumer.py          # Kafka consumer writing to PostgreSQL staging
└── tests/
    ├── test_cleaning.py             # Unit tests for domain cleaners
    ├── test_healthcheck.py          # Infrastructure connectivity tests
    ├── test_ingestion_api.py        # FastAPI endpoint integration tests
    ├── test_streaming.py            # Event ID determinism & envelope tests
    ├── test_validation.py           # Great Expectations suites unit/integration tests
    └── test_warehouse.py            # Dimensional load reconciliation & RBAC tests
```

---

## Infrastructure & Services

All backing infrastructure runs in isolated Docker containers orchestrated via `docker compose`:

| Container Name | Service | Internal Port | Host Port | Role / Credentials | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `orbitwatch_postgres` | PostgreSQL 16 | `5432` | `5433` | `etl_user`, `dashboard_user` | Relational staging, warehouse, audit, and quality schemas |
| `orbitwatch_mongo` | MongoDB 7.0 | `27017` | `27017` | `mongo_admin` | Raw unstructured JSON/CSV telemetry store |
| `orbitwatch_redpanda` | Redpanda v23 | `9092` | `19092` | None (Dev plaintext) | High-performance, Kafka-compatible event broker |
| `orbitwatch_redpanda_console`| Redpanda Console | `8080` | `8080` | None | Interactive UI for Kafka topics, schemas, and consumer groups |

---

## Phase-by-Phase Technical Breakdown

### Phase 1: Infrastructure & Security
- **Containerization:** Configured multi-container Docker Compose with health checks and persistent named volumes.
- **Role-Based Access Control (RBAC):** Established strict principle-of-least-privilege database roles:
  - `etl_user`: Full DDL and DML permissions on `staging`, `dw`, `audit`, and `quality`.
  - `dashboard_user`: Strictly read-only `SELECT` permissions on `dw` (denied access to `staging` or `audit`).
- **Configuration Management:** Centralized Pydantic v2 `BaseSettings` resolving database URIs, broker endpoints, and credentials without hardcoded secrets.

### Phase 2: Exploratory Data Analysis & Cleaning
- **Raw Telemetry Scrapers:** Downloaded SATCAT (70,953 satellites), active/debris GP elements (19,366 ephemerides), solar cycle indices (3,333 months), and geomagnetic K-index (359 records).
- **Domain Cleaning Rules:**
  - Standardized datetime parsing to UTC.
  - Trimmed whitespace and upper-cased natural keys (`NORAD_CAT_ID`, `OBJECT_ID`).
  - Derived orbital regime (`LEO`, `MEO`, `GEO`, `HEO`, `UNKNOWN`) based on mean motion, eccentricity, and apogee/perigee altitudes.
  - Implemented Tukey boxplot interquartile range (IQR) outlier detection for orbital parameters.

### Phase 3: FastAPI Ingestion Microservice
- **REST Ingestion:** Built asynchronous FastAPI service exposing endpoints for payload ingestion (`/ingest/{source}`).
- **Document Store (MongoDB):** Stored raw external payloads in MongoDB collections with composite unique indexes on natural keys (`norad_cat_id + epoch`, `year + month`) to prevent duplicate writes.

### Phase 4: Event-Driven Streaming Pipeline
- **Producer (CDC):** Extracted records from MongoDB and published structured events to Redpanda topics (`orbitwatch.gp`, `orbitwatch.k_index`, `orbitwatch.solar_indices`).
- **Consumer:** Consumed events, validated metadata envelopes (deterministic UUID5 event generation), and inserted raw payloads into `staging.*_raw` tables.
- **Dead-Letter Routing:** Malformed JSON envelopes or corrupted messages were quarantined into `quality.dead_letter`.

### Phase 5: Data Quality Gates (Great Expectations)
- **Two-Tier Quality Gates:**
  1. **Raw Suites:** Validated schema conformance, null constraints, and range bounds (e.g., $0 \le i \le 180^\circ$, $0 \le e < 1.0$, non-future epochs).
  2. **Clean Suites:** Enforced relational referential rules, valid regime categorizations, and launch-before-decay chronological integrity.
- **Automated Quarantine:** Invalid rows bypassed clean tables and were routed into `quality.dead_letter` and error CSVs with explicit reason codes (`INCLINATION_OUT_OF_RANGE`, `DECAY_BEFORE_LAUNCH`).
- **HTML Data Docs:** Compiled interactive, standalone visual validation reports in `docs/validation_report/index.html`.

### Phase 6: Dimensional Warehouse (Schema `dw`)
- **Star Schema Design:** Replaced complex normalized relational joins with Kimball-style dimensional facts and dimensions in schema `dw`.
- **Surrogate Keys:** Integer `date_key` (`YYYYMMDD`) and surrogate `satellite_key` (SCD Type 1).
- **Atomic Loader (`scripts/load_warehouse.py`):** Single-transaction truncate-and-load pipeline guaranteeing zero partial loads.
- **Audit & Lineage:** Every run records execution duration and row throughput in `audit.pipeline_runs` and individual dataset mapping in `audit.data_lineage`.

### Phase 7: Workflow Orchestration (Prefect Flow)
- **Flow DAG (`flows/orbitwatch_flow.py`):** Sequenced ingestion, validation, and warehouse loading into unified Prefect `@task` blocks.
- **Fault-Tolerant Circuit Breakers:** Configured automatic retries (`retries=2`) on ingestion. A failure in data validation automatically halts the pipeline, preventing unverified data from entering the warehouse.
- **Scheduled Deployments:** Embedded a daily cron schedule (`0 2 * * *` UTC) directly in code.

### Phase 8: Lakehouse Layer (Delta Lake + DuckDB)
- **Delta Lake Export (`scripts/export_lakehouse.py`):** Serialized PostgreSQL `dw` tables into columnar Apache Parquet format wrapped with ACID transaction logs (`_delta_log/`) under `data/lake/`.
- **In-Process Vectorized SQL (`scripts/query_lake.py`):** Used embedded DuckDB to query Delta tables directly via PyArrow datasets, demonstrating sub-second analytic queries over millions of records without database locks.

### Phase 9: Operational Intelligence Dashboard (Streamlit)
- **Executive SDA UI (`app/dashboard.py`):** Single-page visualizer connecting as `dashboard_user`.
- **Core Insights:**
  - Real-time KPI counters across satellites, snapshots, solar history, and decays.
  - Orbit regime population breakdown.
  - Dual-axis time series correlating F10.7 solar radio flux against atmospheric satellite decay counts ($r = 0.7060$).
  - Latest orbital mechanics snapshot tables.

### Phase 10: Verification & System Testing
- **Automated Test Suite:** 43 unit and integration tests passing in `tests/` covering domain cleaning, API authentication, streaming, Great Expectations rules, warehouse integrity, and role permissions.
- **Viva Preparation Bank:** Detailed defense guide and architectural trade-off rationales documented in [`docs/viva_notes.md`](file:///c:/Users/PARAM/Desktop/de%20miniproject/orbitwatch/docs/viva_notes.md).

---

## Step-by-Step Manual Execution Guide

If running manually step-by-step from PowerShell or Command Prompt:

### 1. Environment Setup & Docker Initialization
```powershell
# 1. Activate Python virtual environment
.venv\Scripts\activate

# 2. Start backing services
docker compose up -d

# 3. Check connectivity
python scripts/healthcheck.py
```

### 2. Database Migrations
```powershell
python scripts/apply_sql.py sql/migrations/001_initial_schema.sql
python scripts/apply_sql.py sql/migrations/002_audit_tables.sql
python scripts/apply_sql.py sql/migrations/003_staging_tables.sql
python scripts/apply_sql.py sql/migrations/004_clean_tables.sql
python scripts/apply_sql.py sql/migrations/005_star_schema.sql
```

### 3. Ingestion & Streaming Pipeline
```powershell
# Download external telemetry
python src/orbitwatch/ingestion/download_samples.py

# Ingest into MongoDB
python scripts/load_raw_to_mongo.py

# Create streaming topics & stream CDC
python scripts/create_topics.py
python src/orbitwatch/streaming/producer.py --source all
python src/orbitwatch/streaming/consumer.py --once
```

### 4. Validation & Warehouse Loading
```powershell
# Validate staging data with Great Expectations
python scripts/run_validation.py --dataset all

# Load dimensional star schema
python scripts/load_warehouse.py
```

### 5. Lakehouse Export & Analytics
```powershell
python scripts/export_lakehouse.py
python scripts/query_lake.py
```

### 6. Serving Dashboard & Full Testing
```powershell
# Launch Streamlit dashboard
streamlit run app/dashboard.py

# Run complete pytest test suite
pytest -v
```

---

## Auditing, Data Lineage & Dead-Letter Verification

To inspect operational audit metrics and quarantined records, connect to PostgreSQL:

```sql
-- 1. Inspect recent pipeline execution runs
SELECT run_id, pipeline_name, status, rows_in, rows_out, rows_rejected, started_at, finished_at 
FROM audit.pipeline_runs 
ORDER BY started_at DESC 
LIMIT 5;

-- 2. Inspect table-level data lineage
SELECT lineage_id, run_id, source_name, target_name, row_count, created_at 
FROM audit.data_lineage 
ORDER BY lineage_id DESC 
LIMIT 8;

-- 3. Inspect quarantined dead-letter records
SELECT dead_letter_id, source_name, reason_code, left(reason_detail, 60) AS reason, quarantined_at 
FROM quality.dead_letter 
ORDER BY dead_letter_id DESC;

-- 4. Reconcile staging vs warehouse counts
SELECT 
    (SELECT count(*) FROM staging.gp_clean) AS stg_gp,
    (SELECT count(*) FROM dw.fact_gp_snapshot) AS dw_gp,
    (SELECT count(*) FROM staging.solar_indices_clean) AS stg_solar,
    (SELECT count(*) FROM dw.fact_space_weather_month) AS dw_solar,
    (SELECT count(*) FROM staging.satcat_clean WHERE decay_date IS NOT NULL) AS stg_decays,
    (SELECT sum(decay_count) FROM dw.fact_decay_month) AS dw_decays;
```

---

## Physical Insights: Solar Flux vs. Orbital Decay

The correlation between **F10.7 Solar Radio Flux** and **Satellite Atmospheric Re-entries** is one of the core domain highlights of this project:

- **Statistical Metric:** Pearson Correlation Coefficient **$r = 0.7060$** (Strong Positive Correlation over 808 monthly observations).
- **Physical Mechanism:** Extreme Ultraviolet (EUV) emissions from solar active regions heat Earth's thermosphere (200–600 km). This thermal expansion increases neutral atmospheric density at Low Earth Orbit (LEO) altitudes by up to **$10\times$**, drastically multiplying aerodynamic drag ($F_D = \frac{1}{2}\rho v^2 C_D A$) and forcing orbital decay.
- **Scientific Caveat:** *Correlation does not imply causation.* While thermospheric heating is the dominant physical force, total recorded monthly decays are also modulated by human launch cadences, mega-constellation active de-orbiting schedules, and historical tracking station coverage.

---

## Known Limitations & Technical Trade-Offs

1. **Future Epoch Rule Dependency:** Clean GP counts depend on execution date. Great Expectations strictly enforces `EPOCH <= datetime.now(timezone.utc)`. Future-propagated ephemerides are quarantined into dead-letter storage.
2. **K-Index Window Horizon:** The NOAA SWPC 1-minute planetary K-index provides only 359 rolling observations (~24 hours). It is retained in staging and excluded from warehouse facts to avoid multi-decade grain mismatch.
3. **Python 3.13 Runtime:** The project executes on Python 3.13.5. Minor upstream library deprecations exist (Pandas 4 string migration notices and FastAPI lifespan event handlers) without impacting execution.
4. **Synthetic Rejection Testing:** Because production CelesTrak and NOAA SWPC API feeds are curated, natural live rejections are rare. Dead-letter paths were verified through automated fault injection (`--demo-bad-batch` and `test_dlq.py`).

---

## Viva Examination Defense Highlights

- **Why a Star Schema instead of 3NF Core?** Space domain analytics require multi-dimensional slicing across orbital regimes, object types, and solar cycles. Star schemas minimize expensive multi-table joins, provide predictable query optimization paths, and conform date grains.
- **Why SCD Type 1 for `dim_satellite`?** Satellite characteristics in SATCAT (radar cross section, operational status) represent corrections to physical objects rather than operational state changes needing validity date intervals.
- **Why Delta Lake + DuckDB?** Offloading historical analytical scans from PostgreSQL to columnar Delta Lake tables on Parquet eliminates OLTP lock contention while DuckDB provides sub-second vectorized analytical SQL in-process.

---

## License

Developed as an educational Space Domain Awareness Data Engineering project. Telemetry provided courtesy of CelesTrak and the NOAA Space Weather Prediction Center.
