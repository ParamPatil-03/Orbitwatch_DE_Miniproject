# ORBITWATCH

**ORBITWATCH** is a Space Traffic and Debris Data Platform designed to collect, process, and analyze satellite and space-debris tracking data (CelesTrak) alongside space-weather conditions (NOAA SWPC). It is built as a fault-tolerant data engineering project with streaming, relational, and NoSQL storage layers.

## Prerequisites
- Python 3.11
- Docker and Docker Compose (v2 syntax)

## Setup Instructions

1. **Configure Environment Variables**
   Copy the example environment file and fill in your desired passwords:
   ```bash
   cp .env.example .env
   ```
   *(Windows CMD: `copy .env.example .env`)*

2. **Create a Virtual Environment**
   Set up your local Python environment.

   *Windows:*
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```
   *macOS/Linux:*
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Requirements**
   Install the project dependencies defined for all phases:
   ```bash
   pip install -r requirements.txt
   ```

4. **Start Infrastructure Services**
   Spin up the required database and message broker containers:
   ```bash
   docker compose up -d
   ```

5. **Verify the Environment**
   Run the health check script to ensure all services are up and permissions are correctly configured:
   ```bash
   python scripts/healthcheck.py
   ```

## Services Overview

| Service | Host Port | Purpose |
| :--- | :--- | :--- |
| **PostgreSQL 16** | 5432 | Relational store containing staging, warehouse, audit, and quality schemas. |
| **MongoDB 7** | 27017 | NoSQL document store for raw, unstructured API payloads. |
| **Redpanda** | 19092 (host API) | Kafka-compatible streaming broker for event-driven pipelines. |
| **Redpanda Console** | 8080 | Web UI for interacting with Redpanda topics and consumer groups. |

## Resetting Data
To completely wipe all data and start fresh, run:
```bash
docker compose down -v
```
**Warning:** This deletes all container volumes. The SQL initialization scripts (e.g., roles and schemas) will *only* re-run automatically when the PostgreSQL volume is completely empty.

## Troubleshooting
- **Port already in use:** Ensure you do not have a local instance of PostgreSQL (5432), MongoDB (27017), or Kafka/Zookeeper running on your host machine.
- **Docker not running:** Ensure Docker Desktop is open and the Docker daemon is active before running `docker compose`.
- **Redpanda listener errors:** Verify `KAFKA_BOOTSTRAP_SERVERS` in `.env` is set to `localhost:19092` for host-based connections.
- **Init scripts not re-running:** Postgres init scripts only trigger on the very first start of a fresh volume. If you modified `.env` passwords or SQL scripts after starting Postgres, you must run `docker compose down -v` to clear the old volume and re-trigger initialization.

## Roadmap
- [x] Phase 1: Infrastructure and Setup
- [x] Phase 2: Exploratory Data Analysis and Data Cleaning
- [x] Phase 3: FastAPI Ingestion
- [x] Phase 4: Streaming
- [ ] Phase 5: Validation
- [ ] Phase 6: Warehouse and ETL
- [ ] Phase 7: Analytics
- [ ] Phase 8: Orchestration
- [ ] Phase 9: Lakehouse and Scale
- [ ] Phase 10: Dashboard

## Phase 3: FastAPI Ingestion

To start the API, run:
```bash
uvicorn orbitwatch.ingestion.api:app --reload --port 8000 --app-dir src
```
Then, open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser.

To run the bulk loader and ingest the Phase 2 raw files into MongoDB via the API, execute:
```bash
python scripts/load_raw_to_mongo.py
```

## Phase 2: Data Exploration & Cleaning

To run Phase 2 (which downloads samples to `data/raw/`, profiles them, cleans them, and outputs to `data/staging/` and `data/errors/`), execute:
```bash
python scripts/run_phase2.py
```
This generates the `docs/data_profile.md` report and charts in `docs/figures/`.

## Phase 4: Streaming (Kafka to PostgreSQL)

To create the Redpanda topics:
```bash
python scripts/create_topics.py
```

To apply the SQL migration for staging tables:
```bash
python scripts/apply_sql.py sql/migrations/003_staging_tables.sql
```

To stream the MongoDB raw data into Redpanda (Producer):
```bash
python src/orbitwatch/streaming/producer.py --source all
```

To consume the stream and insert it into PostgreSQL staging tables (Consumer):
```bash
python src/orbitwatch/streaming/consumer.py --once
```
