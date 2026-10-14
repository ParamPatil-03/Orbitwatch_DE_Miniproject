#!/usr/bin/env python3
"""
ORBITWATCH – scripts/load_warehouse.py
Phase 6: Warehouse Loader.

Performs idempotent TRUNCATE + INSERT ... SELECT from staging.*_clean tables
into the dimensional warehouse schema 'dw' (Star Schema) in a single transaction.

Grain definitions:
  - dw.fact_gp_snapshot: One row per satellite per epoch observation.
  - dw.fact_space_weather_month: One row per calendar month (F10.7, sunspot number).
  - dw.fact_decay_month: One row per calendar month and orbit regime (decay count).

Audit tracking:
  - Writes execution metrics to audit.pipeline_runs (status guaranteed in finally block).
  - Writes lineage edges to audit.data_lineage.
  - Ensures grants: etl_user full DML; dashboard_user SELECT on dw schema only.
"""

from __future__ import annotations

import datetime
import sys
import uuid
from pathlib import Path
from typing import Dict, Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Add src and root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from orbitwatch.common.db import get_postgres_engine


def load_warehouse(engine: Engine | None = None) -> dict[str, int]:
    """
    Execute the full warehouse dimensional ETL inside a single database transaction.

    Args:
        engine: Optional SQLAlchemy Engine. Defaults to get_postgres_engine("etl").

    Returns:
        dict with row counts loaded for each dimensional and fact table.
    """
    if engine is None:
        engine = get_postgres_engine("etl")

    run_id = str(uuid.uuid4())
    started_at = datetime.datetime.now(datetime.timezone.utc)
    status = "failed"
    counts: dict[str, int] = {}
    rows_in = 0
    rows_out = 0

    try:
        with engine.begin() as conn:
            print("\n[Warehouse] Starting idempotent truncate-and-load into dw...")

            # Insert initial pipeline_runs record so data_lineage foreign key is satisfied
            conn.execute(
                text("""
                    INSERT INTO audit.pipeline_runs
                        (run_id, pipeline_name, status, rows_in, rows_out, rows_rejected,
                         started_at)
                    VALUES
                        (:run_id, 'load_warehouse', 'running', 0, 0, 0, :started_at)
                """),
                {"run_id": run_id, "started_at": started_at},
            )

            # 1. Truncate fact tables and dependent dimensions in reverse dependency order
            conn.execute(text("""
                TRUNCATE TABLE 
                    dw.fact_gp_snapshot,
                    dw.fact_space_weather_month,
                    dw.fact_decay_month,
                    dw.dim_satellite
                CASCADE;
            """))

            # 2. Populate dim_satellite (SCD Type 1) from staging.satcat_clean
            print("[Warehouse] Loading dw.dim_satellite from staging.satcat_clean...")
            res_sat = conn.execute(text("""
                INSERT INTO dw.dim_satellite (
                    norad_cat_id,
                    object_name,
                    object_id,
                    object_type_id,
                    ops_status_code,
                    owner,
                    launch_date,
                    launch_site,
                    decay_date,
                    period,
                    inclination,
                    apogee,
                    perigee,
                    rcs,
                    data_status_code,
                    orbit_center,
                    orbit_type,
                    orbit_regime_id,
                    is_outlier,
                    loaded_at
                )
                SELECT
                    s.norad_cat_id,
                    s.object_name,
                    s.object_id,
                    ot.object_type_id,
                    s.ops_status_code,
                    s.owner,
                    s.launch_date,
                    s.launch_site,
                    s.decay_date,
                    s.period,
                    s.inclination,
                    s.apogee,
                    s.perigee,
                    s.rcs,
                    s.data_status_code,
                    s.orbit_center,
                    s.orbit_type,
                    dor.regime_id,
                    s.is_outlier,
                    now()
                FROM staging.satcat_clean s
                LEFT JOIN dw.dim_object_type ot 
                    ON s.object_type = ot.object_type_code
                LEFT JOIN dw.dim_orbit_regime dor 
                    ON COALESCE(s.orbit_regime, 'UNKNOWN') = dor.regime_code
                ORDER BY s.norad_cat_id;
            """))
            counts["dim_satellite"] = res_sat.rowcount

            # 3. Populate fact_gp_snapshot from staging.gp_clean
            # Grain: One row per satellite per epoch snapshot
            print("[Warehouse] Loading dw.fact_gp_snapshot from staging.gp_clean...")
            res_gp = conn.execute(text("""
                INSERT INTO dw.fact_gp_snapshot (
                    satellite_key,
                    date_key,
                    epoch,
                    orbit_regime_id,
                    inclination,
                    eccentricity,
                    mean_motion,
                    bstar,
                    is_outlier,
                    loaded_at
                )
                SELECT
                    ds.satellite_key,
                    (EXTRACT(YEAR FROM g.epoch)::INT * 10000 
                     + EXTRACT(MONTH FROM g.epoch)::INT * 100 
                     + EXTRACT(DAY FROM g.epoch)::INT) AS date_key,
                    g.epoch,
                    dor.regime_id,
                    g.inclination,
                    g.eccentricity,
                    g.mean_motion,
                    NULLIF(g.bstar, '')::DOUBLE PRECISION,
                    g.is_outlier,
                    now()
                FROM staging.gp_clean g
                JOIN dw.dim_satellite ds 
                    ON g.norad_cat_id = ds.norad_cat_id
                JOIN dw.dim_orbit_regime dor 
                    ON COALESCE(g.orbit_regime, 'UNKNOWN') = dor.regime_code;
            """))
            counts["fact_gp_snapshot"] = res_gp.rowcount

            # 4. Populate fact_space_weather_month from staging.solar_indices_clean
            # Grain: One row per calendar month. Date key uses first day of month (YYYYMM01).
            print("[Warehouse] Loading dw.fact_space_weather_month from staging.solar_indices_clean...")
            res_sw = conn.execute(text("""
                INSERT INTO dw.fact_space_weather_month (
                    date_key,
                    f107,
                    ssn,
                    smoothed_f107,
                    smoothed_ssn,
                    loaded_at
                )
                SELECT
                    (EXTRACT(YEAR FROM s.time_tag::TIMESTAMPTZ)::INT * 10000 
                     + EXTRACT(MONTH FROM s.time_tag::TIMESTAMPTZ)::INT * 100 
                     + 1) AS date_key,
                    s.f107,
                    s.ssn,
                    s.smoothed_f107,
                    s.smoothed_ssn,
                    now()
                FROM staging.solar_indices_clean s;
            """))
            counts["fact_space_weather_month"] = res_sw.rowcount

            # 5. Populate fact_decay_month from staging.satcat_clean
            # Grain: One row per calendar month and orbit regime.
            # Aggregates objects with non-null decay_date in that month.
            print("[Warehouse] Loading dw.fact_decay_month from staging.satcat_clean...")
            res_dec = conn.execute(text("""
                INSERT INTO dw.fact_decay_month (
                    date_key,
                    orbit_regime_id,
                    decay_count,
                    loaded_at
                )
                SELECT
                    (EXTRACT(YEAR FROM s.decay_date)::INT * 10000 
                     + EXTRACT(MONTH FROM s.decay_date)::INT * 100 
                     + 1) AS date_key,
                    dor.regime_id,
                    COUNT(*)::INT AS decay_count,
                    now()
                FROM staging.satcat_clean s
                JOIN dw.dim_orbit_regime dor 
                    ON COALESCE(s.orbit_regime, 'UNKNOWN') = dor.regime_code
                WHERE s.decay_date IS NOT NULL
                GROUP BY 1, 2;
            """))
            counts["fact_decay_month"] = res_dec.rowcount

            # Ensure grants: dashboard_user receives SELECT on dw schema
            conn.execute(text("""
                GRANT USAGE ON SCHEMA dw TO dashboard_user;
                GRANT SELECT ON ALL TABLES IN SCHEMA dw TO dashboard_user;
                GRANT SELECT ON ALL SEQUENCES IN SCHEMA dw TO dashboard_user;
            """))

            # Compute input and output metrics for audit
            staging_counts = conn.execute(text("""
                SELECT 
                    (SELECT count(*) FROM staging.satcat_clean) AS satcat_cnt,
                    (SELECT count(*) FROM staging.gp_clean) AS gp_cnt,
                    (SELECT count(*) FROM staging.solar_indices_clean) AS solar_cnt
            """)).fetchone()
            rows_in = (staging_counts[0] or 0) + (staging_counts[1] or 0) + (staging_counts[2] or 0)
            rows_out = sum(counts.values())

            # Lineage rows for each target table
            lineage_mappings = [
                ("staging.satcat_clean", "dw.dim_satellite", counts["dim_satellite"]),
                ("staging.gp_clean", "dw.fact_gp_snapshot", counts["fact_gp_snapshot"]),
                ("staging.solar_indices_clean", "dw.fact_space_weather_month", counts["fact_space_weather_month"]),
                ("staging.satcat_clean", "dw.fact_decay_month", counts["fact_decay_month"]),
            ]
            for src, tgt, cnt in lineage_mappings:
                conn.execute(
                    text("""
                        INSERT INTO audit.data_lineage
                            (run_id, source_name, target_name, step_name, row_count, recorded_at)
                        VALUES
                            (:run_id, :src, :tgt, 'load_warehouse', :cnt, now())
                    """),
                    {"run_id": run_id, "src": src, "tgt": tgt, "cnt": cnt},
                )

            status = "success"
            print("[Warehouse] Load transaction committed successfully.")

    except Exception as exc:
        print(f"[Warehouse] ERROR during warehouse load: {exc}")
        status = "failed"
        raise

    finally:
        # Audit record updated guaranteed in finally block
        finished_at = datetime.datetime.now(datetime.timezone.utc)
        try:
            with engine.begin() as audit_conn:
                audit_conn.execute(
                    text("""
                        INSERT INTO audit.pipeline_runs
                            (run_id, pipeline_name, status, rows_in, rows_out, rows_rejected,
                             started_at, finished_at, notes)
                        VALUES
                            (:run_id, 'load_warehouse', :status, :rows_in, :rows_out, 0,
                             :started_at, :finished_at, :notes)
                        ON CONFLICT (run_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            rows_in = EXCLUDED.rows_in,
                            rows_out = EXCLUDED.rows_out,
                            finished_at = EXCLUDED.finished_at,
                            notes = EXCLUDED.notes;
                    """),
                    {
                        "run_id": run_id,
                        "status": status,
                        "rows_in": rows_in,
                        "rows_out": rows_out,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "notes": f"Loaded tables: {counts}",
                    },
                )
        except Exception as audit_exc:
            print(f"[Warehouse] Failed to record audit run: {audit_exc}")

    return counts


def main() -> int:
    """CLI entry point for running warehouse load directly."""
    try:
        counts = load_warehouse()
        print("\n" + "=" * 50)
        print("  WAREHOUSE LOAD SUMMARY")
        print("=" * 50)
        for tbl, cnt in counts.items():
            print(f"  dw.{tbl:<28}: {cnt:>8} rows")
        print("=" * 50)
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
