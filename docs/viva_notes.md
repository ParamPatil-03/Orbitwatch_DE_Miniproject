# ORBITWATCH — Comprehensive Viva & Technical Defense Notes

This document provides preparation notes for oral viva examinations, detailing the technical rationale, architectural decisions, and key defense questions across all 10 project phases.

---

## High-Level Summary of Phases 1 to 5

- **Phase 1 (Infrastructure & Setup):** Multi-container Docker Compose stack orchestrating PostgreSQL 16, MongoDB 7, Redpanda (Kafka-compatible broker), and Redpanda Console with dedicated least-privilege roles (`etl_user`, `dashboard_user`).
- **Phase 2 (EDA & Cleaning):** Ingestion of raw CelesTrak and NOAA SWPC telemetry into timestamped CSV/JSON files, accompanied by data profiling reports, domain-specific rule cleaners, and baseline statistical figures.
- **Phase 3 (FastAPI Ingestion):** Authenticated REST microservice ingesting raw external payloads into MongoDB collections (`raw_satcat`, `raw_gp`, `raw_k_index`, `raw_solar`) using natural composite keys for idempotency.
- **Phase 4 (Streaming):** Change-data capture streaming from MongoDB via Redpanda event topics (`orbitwatch.gp`, `orbitwatch.k_index`, `orbitwatch.solar_indices`) consumed into PostgreSQL staging raw tables with DLQ routing for malformed envelopes.
- **Phase 5 (Validation & Quality Gates):** Two-tier Great Expectations (1.x) validation suites (raw and clean) with automated HTML Data Docs compilation, dead-letter routing to `quality.dead_letter`, and comprehensive audit tracking in `audit.pipeline_runs`.

---

## Phase 6: Dimensional Warehouse (Star Schema in Schema "dw")

### What it Does
Transforms relational staging clean tables (`staging.gp_clean`, `staging.satcat_clean`, `staging.solar_indices_clean`) into a Kimball-style dimensional star schema residing in the `dw` schema.
- **Dimensions:**
  - `dim_date`: Generated calendar dimension (1749 to 2030, covering 102,998 calendar days) keyed by surrogate integer `YYYYMMDD`.
  - `dim_satellite`: Surrogate key `satellite_key`, SCD Type 1 tracking NORAD ID, object name, launch date, decay date, apogee, perigee, and orbital regime.
  - `dim_orbit_regime`: Conformed reference dimension (LEO, MEO, GEO, HEO, UNKNOWN).
  - `dim_object_type`: Standard object types (Payload, Rocket Body, Debris, Unknown).
- **Facts:**
  - `fact_gp_snapshot`: Grain = one row per satellite per epoch snapshot (19,366 rows).
  - `fact_space_weather_month`: Grain = one row per calendar month with F10.7 solar radio flux and sunspot numbers (3,333 rows).
  - `fact_decay_month`: Grain = one row per calendar month per orbit regime recording total satellite re-entry decays (1,535 rows, 35,677 total decays).
- **ETL Loader (`scripts/load_warehouse.py`):**
  - Executes as a single idempotent atomic transaction: `BEGIN ... TRUNCATE ... INSERT INTO ... COMMIT`.
  - Automatically records pipeline status and duration in `audit.pipeline_runs` within a `finally` block.
  - Inserts individual table lineage records into `audit.data_lineage`.
  - Grants read-only `SELECT` permissions on `dw` to `dashboard_user`.

### Why This Design?
1. **Star Schema vs. 3NF Core:** Analytic queries across space domain awareness require slicing satellite dynamics across time, orbital regime, and solar cycles. A star schema minimizes joins, enables predictable query plans, and supports columnar vectorization, whereas normalized 3NF structures increase join complexity for reporting users.
2. **Calendar Surrogate Key (`YYYYMMDD`):** Integer date keys eliminate runtime timestamp parsing overhead, support efficient range partitioning, and standardize joins across daily snapshots and monthly aggregated space weather.
3. **Monthly Grain for Weather & Decays:** Atmospheric decay is an integrated drag phenomenon driven by multi-week solar ultraviolet heating. Aligning both weather and decay counts to the first day of the month (`YYYYMM01`) produces a clean, conformed temporal grain.

### Viva Defense Questions & Answers
1. **Q: Why was K-index omitted from the warehouse fact tables?**
   *A:* The NOAA planetary K-index dataset provided only 359 minute-by-minute observations covering a rolling 24-hour window, whereas solar radio flux and decay records span over 70 years. Creating a fact table for 359 short-window rows would introduce a severe grain mismatch and sparse analytics.
2. **Q: Why is `dim_satellite` modeled as SCD Type 1 instead of SCD Type 2?**
   *A:* Orbital characteristics in SATCAT (such as revised operational status or updated radar cross section) represent corrections to physical attributes rather than historical state intervals for tracking. SCD Type 1 was chosen to keep satellite metadata minimal, student-level, and fast to query without complex validity date filters.
3. **Q: How does `scripts/load_warehouse.py` ensure zero data loss during load failures?**
   *A:* The entire truncate-and-load pipeline runs within a single PostgreSQL ACID transaction context. If any `INSERT ... SELECT` fails or a foreign key check raises an exception, the transaction automatically issues a `ROLLBACK`, leaving existing warehouse tables completely intact.

---

## Phase 7: Orchestration (Prefect Flow)

### What it Does
Orchestrates the entire end-to-end data pipeline using Prefect (`flows/orbitwatch_flow.py`).
- **Sequential Pipeline Tasks:**
  1. `download_raw_data_task`: Downloads raw telemetry samples from CelesTrak and NOAA SWPC with automated retries (`retries=2`, `retry_delay_seconds=2`).
  2. `run_data_validation_task`: Executes Great Expectations suites across staging tables (`scripts/run_validation.py --dataset all`).
  3. `load_data_warehouse_task`: Runs the dimensional warehouse loader (`scripts/load_warehouse.py`).
- **Control Flow:**
  - Tasks execute in strict serial dependency. If any upstream task fails (such as network failure during ingestion), downstream validation and warehouse loading are immediately blocked.
  - Implements a scheduled cron definition (`0 2 * * *` UTC) defined in code for scheduled deployment.

### Why This Design?
1. **Prefect Subprocess Encapsulation:** Rather than rewriting working Phase 2, 5, and 6 code into monolithic Prefect functions, the tasks invoke the tested entry points with controlled `PYTHONPATH` environments. This preserves modularity and keeps production scripts decoupled from the orchestration engine.
2. **Fail-Fast Safety Gate:** Preventing dirty or unvalidated data from reaching the analytics warehouse is a core data engineering tenet. By enforcing task chaining, a failure in data validation stops the warehouse load before any table truncation occurs.

### Viva Defense Questions & Answers
1. **Q: What happens if an API endpoint is unreachable during ingestion?**
   *A:* The `download_raw_data_task` catches the network timeout and attempts 2 retries spaced 2 seconds apart. If all retries fail, the task raises an exception, marked as `Failed`, and downstream validation and warehouse load tasks do not execute.
2. **Q: Why use Prefect over Apache Airflow for this project?**
   *A:* Prefect provides pure-Python decorator-based task graphs (`@flow`, `@task`) without requiring heavyweight separate scheduler, worker, and webserver containers, making it lightweight, developer-friendly, and ideal for local execution while retaining full observability.
3. **Q: How are pipeline execution metrics audited during flow runs?**
   *A:* In addition to Prefect's state tracking engine, each individual pipeline stage logs operational execution rows directly into PostgreSQL `audit.pipeline_runs` and `audit.data_lineage`, providing database-native auditability independent of the orchestrator.

---

## Phase 8: Lakehouse Export (Delta Lake + DuckDB)

### What it Does
Establishes a hybrid Lakehouse architecture by exporting relational warehouse tables to ACID Delta Lake tables in `data/lake/` and querying them with DuckDB.
- **Export Loader (`scripts/export_lakehouse.py`):**
  - Reads `dw.fact_gp_snapshot`, `dw.fact_space_weather_month`, `dw.fact_decay_month`, and `dw.dim_satellite`.
  - Serializes data into Apache Parquet format wrapped with Delta transaction logs (`_delta_log/`) using `deltalake.write_deltalake(..., mode="overwrite")`.
  - Increments Delta table transaction versions (version 0 on initial write, version 1 on second overwrite).
- **Embedded Analytical Querying (`scripts/query_lake.py`):**
  - Uses DuckDB with zero server overhead to read Delta tables via PyArrow datasets.
  - Query 1: Top 10 historical months by total satellite decay count.
  - Query 2: Multi-decade monthly F10.7 solar radio flux versus satellite decay count.
  - Delta History Inspection: Displays transaction commit version, operations, and row counts directly from `_delta_log`.

### Why This Design?
1. **Delta Lake Storage Layer:** Delta Lake adds ACID transaction guarantees, schema enforcement, and time-travel versioning on top of standard Parquet files, preventing partial file reads during export jobs.
2. **DuckDB In-Process Engine:** DuckDB executes vectorized analytical SQL directly inside the Python process without requiring an external cluster (like Spark or Trino), providing sub-second analytical execution on local hardware.

### Viva Defense Questions & Answers
1. **Q: What is the benefit of exporting PostgreSQL tables to Delta Lake?**
   *A:* Relational databases (OLTP) suffer performance degradation under high-throughput analytical scans. Delta Lake decoupled storage on Parquet enables cloud object store archiving, columnar compression, and concurrent analytical queries without impacting database CPU or lock managers.
2. **Q: How does DuckDB avoid reading stale or tombstoned files after an overwrite export?**
   *A:* `DeltaTable.to_pyarrow_dataset()` parses the `_delta_log` JSON commit logs first, filtering out tombstoned Parquet files and passing only active transaction snapshots to DuckDB's vectorized query engine.
3. **Q: How does Delta Lake handle schema evolution?**
   *A:* Delta Lake enforces strict schema matching on append/overwrite by default. If upstream column schemas change, Delta allows controlled schema merging (`mergeSchema=True`) or explicit table migrations without corrupting legacy data files.

---

## Phase 9: Dashboard & Serving (Streamlit)

### What it Does
Delivers an interactive space domain awareness executive dashboard in `app/dashboard.py`.
- **Role-Based Security:**
  - Authenticates strictly using `dashboard_user` credentials via `get_postgres_engine("dashboard")`.
  - Restricts access to `SELECT` on `dw.*`, verified on startup (`SELECT current_user`).
- **Telemetry Visualizations:**
  1. **Summary KPIs:** Catalogued satellites (70,953), active GP snapshots (19,366), space weather months (3,333), and atmospheric decays (35,677).
  2. **Orbit Regime Distribution:** Bar breakdown and data table showing satellite populations (LEO: 62,290; MEO: 3,688; UNKNOWN: 2,052; HEO: 1,986; GEO: 937).
  3. **Dual-Axis Drag Correlation Analysis:** Secondary y-axis time series charting F10.7 solar radio flux against satellite decay counts over 70+ years.
  4. **Statistical Rigor:** Pearson correlation coefficient ($r = 0.7060$, strong positive) with an explicit causation caveat on solar atmospheric heating and orbital lifetime.
  5. **GP Mechanics Table:** Summary orbital mechanics (mean motion, eccentricity, inclination) across orbital regimes.

### Why This Design?
1. **Principle of Least Privilege:** Connecting via `dashboard_user` guarantees that analytical dashboards cannot execute DDL, `TRUNCATE`, or `UPDATE` operations, protecting the dimensional warehouse from reporting tool exploits.
2. **Dual-Axis Charting with Correlation:** Physical atmospheric drag is driven by solar extreme ultraviolet (EUV) radiation (indexed by F10.7 flux) expanding Earth's thermosphere. Plotting solar flux and re-entries together makes this physical phenomenon visually intuitive.

### Viva Defense Questions & Answers
1. **Q: Why was `dashboard_user` granted access only to the `dw` schema and not `staging`?**
   *A:* Staging tables contain intermediate, unvalidated, or duplicate raw records. Exposing staging to reporting users risks metric discrepancies and exposes unmasked internal ETL state.
2. **Q: What is the physical explanation for the $r = 0.706$ correlation between F10.7 and decays?**
   *A:* During solar maximum, increased solar ultraviolet and X-ray emission heats the upper atmosphere, causing thermospheric expansion. Neutral density at LEO altitudes (300–600 km) increases by up to an order of magnitude, increasing aerodynamic drag on satellites and accelerating orbital decay.
3. **Q: Why is the causation caveat mandatory when presenting this correlation?**
   *A:* While solar drag is a dominant physical driver of decay, total observed re-entries are also heavily influenced by human launch volume, mega-constellation end-of-life deorbiting strategies, and historical tracking station coverage. High correlation does not imply solar flux is the sole causative factor.

---

## Phase 10: System Integration & Full Verification

### What it Does
Consolidates the complete data engineering lifecycle into reproducible documentation, end-to-end execution commands, automated regression suites, and verified architectural artifacts.
- End-to-end automated pytest suite: 43 passing unit and integration tests.
- Zero orphan foreign keys and 100% stage-to-warehouse reconciliation.
- Complete audit trails in `audit.pipeline_runs` and `audit.data_lineage`.

---

## Honest Known Limitations

1. **Clean GP Counts Depend on Run Date (Future-Epoch Rule):**
   The Great Expectations suite for GP data validates that orbital snapshot `EPOCH <= datetime.now(timezone.utc)`. If raw telemetry contains future-dated propagation ephemerides or if the system clock skews, rows will be rejected into the dead-letter queue.
2. **NOAA Planetary K-Index Dataset Short Window:**
   The SWPC 1-minute planetary K-index feed provides only 359 rolling observations covering ~24 hours. Because the solar cycle and decay facts cover decades, K-index was kept in staging and intentionally excluded from star schema fact tables to prevent grain distortion.
3. **Python Runtime 3.13 vs. Original Specification 3.11:**
   The host machine runs Python 3.13.5 instead of the initial spec Python 3.11. While all libraries (SQLAlchemy, psycopg, Polars, Great Expectations, Prefect, Delta Lake, DuckDB, Streamlit) execute successfully, deprecation notices exist (e.g., Pandas 4 string migration warnings and FastAPI lifespan handlers).
4. **Reject Path Exercised Primarily in Tests:**
   The production live feeds from CelesTrak and NOAA SWPC are generally well-curated, meaning legitimate clean ingestion typically produces zero schema rejections. The dead-letter and error-routing logic was verified through deliberate fault injection (`--demo-bad-batch` and `tests/test_validation.py`).
