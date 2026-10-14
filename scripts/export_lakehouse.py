"""
ORBITWATCH – scripts/export_lakehouse.py
Phase 8: Export dimensional warehouse tables from PostgreSQL dw schema
to Delta Lake tables under data/lake/.

Tables exported:
  - dw.fact_gp_snapshot
  - dw.fact_space_weather_month
  - dw.fact_decay_month
  - dw.dim_satellite

Uses deltalake Python library to write ACID Delta tables with Parquet storage.
Supports idempotent overwrite on subsequent runs.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
from deltalake import DeltaTable, write_deltalake

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from orbitwatch.common.db import get_postgres_engine
from orbitwatch.common.logging_setup import get_logger

logger = get_logger("export_lakehouse")

TABLES_TO_EXPORT = [
    "fact_gp_snapshot",
    "fact_space_weather_month",
    "fact_decay_month",
    "dim_satellite",
]


def export_table_to_delta(table_name: str, lake_dir: Path, engine: Any) -> int:
    """Read a table from dw schema and write to Delta table under lake_dir with overwrite."""
    dest_path = lake_dir / table_name
    query = f"SELECT * FROM dw.{table_name}"
    
    start_t = time.time()
    df = pd.read_sql(query, engine)
    read_duration = time.time() - start_t
    
    # Overwrite mode ensures idempotency while maintaining Delta Lake transaction history
    write_deltalake(dest_path, df, mode="overwrite")
    write_duration = time.time() - start_t - read_duration
    
    dt = DeltaTable(dest_path)
    version = dt.version()
    
    print(f"  [OK] Exported dw.{table_name:<25} -> {table_name}/ "
          f"({len(df):>6} rows, v{version}, read {read_duration:.2f}s, write {write_duration:.2f}s)")
    return len(df)


def run_export() -> dict[str, int]:
    """Execute export for all target tables and return row counts."""
    lake_dir = ROOT / "data" / "lake"
    lake_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "=" * 70)
    print("  ORBITWATCH - DELTA LAKEHOUSE EXPORT")
    print(f"  Target directory: {lake_dir}")
    print("=" * 70)
    
    engine = get_postgres_engine("etl")
    counts: dict[str, int] = {}
    
    for table_name in TABLES_TO_EXPORT:
        row_count = export_table_to_delta(table_name, lake_dir, engine)
        counts[table_name] = row_count
        
    print("=" * 70)
    print(f"  SUCCESS: Exported {len(counts)} tables to Delta Lake format.\n")
    return counts


if __name__ == "__main__":
    run_export()
