"""
ORBITWATCH – scripts/query_lake.py
Phase 8: DuckDB queries over exported Delta Lake tables in data/lake/.

Queries:
  1. Top 10 months by satellite decay count.
  2. Monthly F10.7 solar radio flux vs. satellite decay count.
  3. Delta table transaction history and version inspection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
from deltalake import DeltaTable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

LAKE_DIR = ROOT / "data" / "lake"


def get_duckdb_connection() -> duckdb.DuckDBPyConnection:
    """Initialize DuckDB and register Delta tables as in-memory views."""
    con = duckdb.connect()
    
    tables = [
        "fact_decay_month",
        "fact_space_weather_month",
        "fact_gp_snapshot",
        "dim_satellite",
    ]
    
    for tbl in tables:
        tbl_path = LAKE_DIR / tbl
        if not tbl_path.exists():
            raise FileNotFoundError(f"Delta table {tbl_path} not found. Run scripts/export_lakehouse.py first.")
        dt = DeltaTable(tbl_path)
        con.register(tbl, dt.to_pyarrow_dataset())
        
    return con


def query_top_decay_months(con: duckdb.DuckDBPyConnection) -> None:
    """Query 1: Top 10 months by total satellite decay count."""
    print("\n" + "=" * 70)
    print("  QUERY 1: TOP 10 MONTHS BY SATELLITE DECAY COUNT")
    print("=" * 70)
    
    query = """
    SELECT 
        CAST(date_key / 10000 AS INTEGER) AS year,
        CAST((date_key % 10000) / 100 AS INTEGER) AS month,
        date_key,
        SUM(decay_count) AS total_decays
    FROM fact_decay_month
    GROUP BY date_key
    ORDER BY total_decays DESC
    LIMIT 10;
    """
    df = con.execute(query).df()
    print(df.to_string(index=False))


def query_f107_vs_decays(con: duckdb.DuckDBPyConnection) -> None:
    """Query 2: Monthly F10.7 Solar Flux vs. Satellite Decay Count."""
    print("\n" + "=" * 70)
    print("  QUERY 2: MONTHLY F10.7 SOLAR FLUX VS SATELLITE DECAY COUNT (RECENT 15)")
    print("=" * 70)
    
    query = """
    SELECT 
        w.date_key,
        CAST(w.date_key / 10000 AS INTEGER) AS year,
        CAST((w.date_key % 10000) / 100 AS INTEGER) AS month,
        ROUND(w.f107, 2) AS f107_solar_flux,
        ROUND(w.ssn, 1) AS sunspot_number,
        d.total_decays
    FROM fact_space_weather_month w
    INNER JOIN (
        SELECT date_key, SUM(decay_count) AS total_decays
        FROM fact_decay_month
        GROUP BY date_key
    ) d ON w.date_key = d.date_key
    ORDER BY w.date_key DESC
    LIMIT 15;
    """
    df = con.execute(query).df()
    print(df.to_string(index=False))


def show_delta_history(table_name: str = "fact_decay_month") -> None:
    """Query 3: Display Delta Lake transaction log / version history."""
    print("\n" + "=" * 70)
    print(f"  DELTA LAKE TRANSACTION HISTORY: {table_name}")
    print("=" * 70)
    
    tbl_path = LAKE_DIR / table_name
    dt = DeltaTable(tbl_path)
    print(f"Current Delta Table Version: {dt.version()}")
    
    history = dt.history()
    print(f"Total Transactions in Log: {len(history)}")
    for commit in history:
        v = commit.get("version", "?")
        ts = commit.get("timestamp", "?")
        op = commit.get("operation", "?")
        metrics = commit.get("operationMetrics", {})
        rows = metrics.get("num_added_rows", "?")
        print(f"  - Version {v}: op={op}, rows={rows}, timestamp={ts}")


def main() -> None:
    con = get_duckdb_connection()
    query_top_decay_months(con)
    query_f107_vs_decays(con)
    show_delta_history("fact_decay_month")
    print("\n" + "=" * 70)
    print("  DUCKDB LAKEHOUSE QUERIES COMPLETE.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
