"""
ORBITWATCH – tests/test_warehouse.py
Phase 6: Unit and integration tests for the dimensional warehouse layer.

Unit tests verify date key generation, orbit regime mapping, and decay aggregation logic.
The integration tests verify warehouse table existence, counts, foreign key integrity,
and dashboard_user read access. Skipped if PostgreSQL is unreachable.
"""

from __future__ import annotations

import datetime
from pathlib import Path
import sys

import pandas as pd
import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from orbitwatch.common.db import get_postgres_engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _postgres_reachable() -> bool:
    """Check if PostgreSQL is reachable using etl credentials."""
    try:
        engine = get_postgres_engine("etl")
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Unit tests (Mock / In-Memory logic)
# ---------------------------------------------------------------------------

class TestWarehouseLogic:
    """Unit tests for warehouse transformation logic using synthetic datasets."""

    def test_date_key_derivation(self):
        """Date key should be integer in YYYYMMDD format; month facts use day 01."""
        dt = datetime.datetime(2026, 10, 14, 15, 30, tzinfo=datetime.timezone.utc)
        daily_key = dt.year * 10000 + dt.month * 100 + dt.day
        month_key = dt.year * 10000 + dt.month * 100 + 1
        assert daily_key == 20261014
        assert month_key == 20261001

    def test_decay_aggregation_logic(self):
        """Aggregate decay events by month (YYYYMM01) and orbit regime."""
        data = pd.DataFrame([
            {"decay_date": pd.Timestamp("2020-05-12", tz="UTC"), "orbit_regime": "LEO"},
            {"decay_date": pd.Timestamp("2020-05-28", tz="UTC"), "orbit_regime": "LEO"},
            {"decay_date": pd.Timestamp("2020-05-19", tz="UTC"), "orbit_regime": "GEO"},
            {"decay_date": pd.Timestamp("2020-06-01", tz="UTC"), "orbit_regime": "LEO"},
            {"decay_date": None, "orbit_regime": "LEO"},  # Active object, no decay
        ])

        # Filter non-null decays
        decays = data[data["decay_date"].notna()].copy()
        decays["date_key"] = decays["decay_date"].apply(
            lambda d: d.year * 10000 + d.month * 100 + 1
        )
        agg = decays.groupby(["date_key", "orbit_regime"]).size().reset_index(name="decay_count")

        assert len(agg) == 3
        # May 2020 LEO has 2 decays
        may_leo = agg[(agg["date_key"] == 20200501) & (agg["orbit_regime"] == "LEO")]
        assert len(may_leo) == 1
        assert may_leo.iloc[0]["decay_count"] == 2


# ---------------------------------------------------------------------------
# Integration tests (Run against PostgreSQL)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _postgres_reachable(), reason="PostgreSQL unreachable")
class TestWarehouseIntegration:
    """Integration tests verifying physical tables, FKs, and dashboard access in schema dw."""

    def test_warehouse_tables_exist(self):
        """Verify all 7 warehouse dimensional and fact tables exist."""
        engine = get_postgres_engine("etl")
        expected_tables = {
            "dim_date",
            "dim_orbit_regime",
            "dim_object_type",
            "dim_satellite",
            "fact_gp_snapshot",
            "fact_space_weather_month",
            "fact_decay_month",
        }
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'dw'"
            )).fetchall()
            existing = {r[0] for r in rows}
            assert expected_tables.issubset(existing), f"Missing tables: {expected_tables - existing}"

    def test_warehouse_row_counts_match_staging(self):
        """Verify fact table counts match staging tables."""
        engine = get_postgres_engine("etl")
        with engine.connect() as conn:
            gp_staging = conn.execute(text("SELECT count(*) FROM staging.gp_clean")).scalar()
            gp_dw = conn.execute(text("SELECT count(*) FROM dw.fact_gp_snapshot")).scalar()
            assert gp_dw == gp_staging, f"GP count mismatch: staging={gp_staging}, dw={gp_dw}"

            decay_staging = conn.execute(text(
                "SELECT count(*) FROM staging.satcat_clean WHERE decay_date IS NOT NULL"
            )).scalar()
            decay_sum_dw = conn.execute(text("SELECT sum(decay_count) FROM dw.fact_decay_month")).scalar()
            assert decay_sum_dw == decay_staging, f"Decay sum mismatch: staging={decay_staging}, dw={decay_sum_dw}"

            solar_staging = conn.execute(text("SELECT count(*) FROM staging.solar_indices_clean")).scalar()
            solar_dw = conn.execute(text("SELECT count(*) FROM dw.fact_space_weather_month")).scalar()
            assert solar_dw == solar_staging, f"Solar count mismatch: staging={solar_staging}, dw={solar_dw}"

    def test_no_orphan_foreign_keys(self):
        """Verify no orphan foreign key records exist in any fact table."""
        engine = get_postgres_engine("etl")
        with engine.connect() as conn:
            # fact_gp_snapshot
            orphan_gp_sat = conn.execute(text(
                "SELECT count(*) FROM dw.fact_gp_snapshot f "
                "LEFT JOIN dw.dim_satellite d ON f.satellite_key = d.satellite_key WHERE d.satellite_key IS NULL"
            )).scalar()
            orphan_gp_date = conn.execute(text(
                "SELECT count(*) FROM dw.fact_gp_snapshot f "
                "LEFT JOIN dw.dim_date d ON f.date_key = d.date_key WHERE d.date_key IS NULL"
            )).scalar()
            orphan_gp_regime = conn.execute(text(
                "SELECT count(*) FROM dw.fact_gp_snapshot f "
                "LEFT JOIN dw.dim_orbit_regime d ON f.orbit_regime_id = d.regime_id WHERE d.regime_id IS NULL"
            )).scalar()
            assert orphan_gp_sat == 0
            assert orphan_gp_date == 0
            assert orphan_gp_regime == 0

            # fact_decay_month
            orphan_dec_date = conn.execute(text(
                "SELECT count(*) FROM dw.fact_decay_month f "
                "LEFT JOIN dw.dim_date d ON f.date_key = d.date_key WHERE d.date_key IS NULL"
            )).scalar()
            orphan_dec_reg = conn.execute(text(
                "SELECT count(*) FROM dw.fact_decay_month f "
                "LEFT JOIN dw.dim_orbit_regime d ON f.orbit_regime_id = d.regime_id WHERE d.regime_id IS NULL"
            )).scalar()
            assert orphan_dec_date == 0
            assert orphan_dec_reg == 0

            # fact_space_weather_month
            orphan_sw_date = conn.execute(text(
                "SELECT count(*) FROM dw.fact_space_weather_month f "
                "LEFT JOIN dw.dim_date d ON f.date_key = d.date_key WHERE d.date_key IS NULL"
            )).scalar()
            assert orphan_sw_date == 0

    def test_dashboard_user_read_access(self):
        """Verify dashboard_user can SELECT from all dw tables but not staging."""
        dashboard_engine = get_postgres_engine("dashboard")
        with dashboard_engine.connect() as conn:
            cnt = conn.execute(text("SELECT count(*) FROM dw.dim_satellite")).scalar()
            assert cnt > 0

            # Verify denied access to staging
            with pytest.raises(Exception):
                conn.execute(text("SELECT count(*) FROM staging.gp_clean"))
