"""
ORBITWATCH – tests/test_validation.py
Phase 5: Unit and integration tests for the validation layer.

Unit tests use hand-crafted DataFrames — no services required.
The integration test is skipped when Postgres or Mongo is unreachable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from orbitwatch.etl.cleaning import clean_gp
from orbitwatch.validation.suites import (
    build_gp_clean_suite,
    build_gp_raw_suite,
    build_k_index_raw_suite,
    build_satcat_raw_suite,
    build_solar_raw_suite,
    run_suite,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(suite, df):
    """Run a GX suite against df using the shared runner."""
    return run_suite(suite, df)


def _failed_expectations(result) -> set[str]:
    return {r.expectation_config.type for r in result.results if not r.success}


# ---------------------------------------------------------------------------
# GP orbit_regime tests (Task 2)
# ---------------------------------------------------------------------------

class TestOrbitRegime:
    """Unit tests for the orbit_regime computation in clean_gp."""

    def _make_row(self, mean_motion: float, eccentricity: float) -> pd.DataFrame:
        """Build a single valid GP row."""
        return pd.DataFrame([{
            "NORAD_CAT_ID": "99999",
            "EPOCH": "2025-01-01T00:00:00",
            "INCLINATION": "45.0",
            "ECCENTRICITY": str(eccentricity),
            "MEAN_MOTION": str(mean_motion),
            "OBJECT_NAME": "TEST",
            "OBJECT_ID": "TEST",
        }])

    def test_leo_case(self):
        """ISS-like orbit: ~15.5 rev/day, e≈0 → LEO (apogee < 2000 km)."""
        df = self._make_row(mean_motion=15.5, eccentricity=0.001)
        clean_df, rejected_df, _ = clean_gp(df)
        assert rejected_df.empty, f"Unexpected rejection: {rejected_df[['reason_code','reason_detail']].to_dict()}"
        assert not clean_df.empty
        assert clean_df.iloc[0]["orbit_regime"] == "LEO"

    def test_geo_case(self):
        """GEO orbit: ~1.0027 rev/day, e≈0 → GEO (35500 ≤ apo ≤ 36000)."""
        df = self._make_row(mean_motion=1.0027, eccentricity=0.0001)
        clean_df, rejected_df, _ = clean_gp(df)
        assert rejected_df.empty
        assert not clean_df.empty
        assert clean_df.iloc[0]["orbit_regime"] == "GEO"


# ---------------------------------------------------------------------------
# GP RAW suite unit tests
# ---------------------------------------------------------------------------

class TestGpRawSuite:
    """Unit tests for the GP RAW expectation suite."""

    def _good_df(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "NORAD_CAT_ID": "900",
            "EPOCH": pd.Timestamp("2025-01-01", tz="UTC"),
            "INCLINATION": 45.0,
            "ECCENTRICITY": 0.001,
            "MEAN_MOTION": 15.5,
        }])

    def test_good_frame_passes(self):
        result = _run(build_gp_raw_suite(), self._good_df())
        assert result.success, f"Expected PASS, got failures: {_failed_expectations(result)}"

    def test_null_norad_caught(self):
        df = self._good_df()
        df["NORAD_CAT_ID"] = None
        result = _run(build_gp_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_values_to_not_be_null" in failed

    def test_inclination_out_of_range_caught(self):
        df = self._good_df()
        df["INCLINATION"] = 200.0
        result = _run(build_gp_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_values_to_be_between" in failed

    def test_eccentricity_ge_1_caught(self):
        df = self._good_df()
        df["ECCENTRICITY"] = 1.5
        result = _run(build_gp_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_values_to_be_between" in failed

    def test_negative_mean_motion_caught(self):
        df = self._good_df()
        df["MEAN_MOTION"] = -5.0
        result = _run(build_gp_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_values_to_be_between" in failed

    def test_null_epoch_caught(self):
        df = self._good_df()
        df["EPOCH"] = None
        result = _run(build_gp_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_values_to_not_be_null" in failed

    def test_future_epoch_caught(self):
        df = self._good_df()
        df["EPOCH"] = pd.Timestamp("2099-01-01", tz="UTC")
        result = _run(build_gp_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_values_to_be_between" in failed


# ---------------------------------------------------------------------------
# GP CLEAN suite unit tests
# ---------------------------------------------------------------------------

class TestGpCleanSuite:
    """Unit tests for the GP CLEAN expectation suite."""

    def _good_clean_df(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "norad_cat_id": "900",
            "epoch": pd.Timestamp("2025-01-01", tz="UTC"),
            "inclination": 45.0,
            "eccentricity": 0.001,
            "mean_motion": 15.5,
            "orbit_regime": "LEO",
        }])

    def test_good_frame_passes(self):
        result = _run(build_gp_clean_suite(), self._good_clean_df())
        assert result.success

    def test_bad_orbit_regime_caught(self):
        df = self._good_clean_df()
        df["orbit_regime"] = "INVALID_REGIME"
        result = _run(build_gp_clean_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_values_to_be_in_set" in failed


# ---------------------------------------------------------------------------
# SATCAT RAW suite unit tests
# ---------------------------------------------------------------------------

class TestSatcatRawSuite:
    """Unit tests for the SATCAT RAW suite, including the null decay_date rule."""

    def _good_satcat_df(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "NORAD_CAT_ID": "25544",
            "OBJECT_TYPE": "PAY",
            "APOGEE": 420.0,
            "PERIGEE": 410.0,
            "LAUNCH_DATE": pd.Timestamp("2020-01-01", tz="UTC"),
            "DECAY_DATE": None,  # null is ALLOWED
        }])

    def test_good_frame_passes(self):
        result = _run(build_satcat_raw_suite(), self._good_satcat_df())
        assert result.success, f"Failures: {_failed_expectations(result)}"

    def test_null_decay_date_is_not_a_failure(self):
        """Null DECAY_DATE must NOT trigger a failure — active satellites have no decay date."""
        df = self._good_satcat_df()
        df["DECAY_DATE"] = None  # explicitly null
        result = _run(build_satcat_raw_suite(), df)
        assert result.success, "Null DECAY_DATE should be allowed"

    def test_null_norad_caught(self):
        df = self._good_satcat_df()
        df["NORAD_CAT_ID"] = None
        result = _run(build_satcat_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_values_to_not_be_null" in failed

    def test_perigee_exceeds_apogee_caught(self):
        df = self._good_satcat_df()
        df["APOGEE"] = 400.0
        df["PERIGEE"] = 500.0  # perigee > apogee
        result = _run(build_satcat_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_pair_values_a_to_be_greater_than_b" in failed

    def test_future_launch_date_caught(self):
        df = self._good_satcat_df()
        df["LAUNCH_DATE"] = pd.Timestamp("2099-01-01", tz="UTC")
        result = _run(build_satcat_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_values_to_be_between" in failed

    def test_decay_before_launch_caught(self):
        df = self._good_satcat_df()
        df["LAUNCH_DATE"] = pd.Timestamp("2020-01-01", tz="UTC")
        df["DECAY_DATE"] = pd.Timestamp("2019-01-01", tz="UTC")
        result = _run(build_satcat_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_pair_values_a_to_be_greater_than_b" in failed


# ---------------------------------------------------------------------------
# K-index RAW suite tests
# ---------------------------------------------------------------------------

class TestKIndexRawSuite:
    def _good_df(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "time_tag": "2025-01-01T00:00:00",
            "kp_index": 3.0,
        }])

    def test_good_frame_passes(self):
        result = _run(build_k_index_raw_suite(), self._good_df())
        assert result.success

    def test_kp_out_of_range_caught(self):
        df = self._good_df()
        df["kp_index"] = 15.0  # > 9
        result = _run(build_k_index_raw_suite(), df)
        failed = _failed_expectations(result)
        assert "expect_column_values_to_be_between" in failed


# ---------------------------------------------------------------------------
# Solar RAW suite tests
# ---------------------------------------------------------------------------

class TestSolarRawSuite:
    def _good_df(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "time_tag": "2025-01",
            "f107": 150.0,
            "ssn": 100.0,
        }])

    def test_good_frame_passes(self):
        result = _run(build_solar_raw_suite(), self._good_df())
        assert result.success


# ---------------------------------------------------------------------------
# Integration test (skipped if services unreachable)
# ---------------------------------------------------------------------------

def _postgres_reachable() -> bool:
    try:
        from orbitwatch.common.db import get_postgres_engine
        engine = get_postgres_engine("etl")
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception:
        return False


def _mongo_reachable() -> bool:
    try:
        from orbitwatch.common.db import get_mongo_client
        client = get_mongo_client()
        client.admin.command("ping")
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not (_postgres_reachable() and _mongo_reachable()),
    reason="Postgres or MongoDB not reachable — skipping integration test",
)
def test_integration_loaders():
    """Integration test: loaders return non-empty DataFrames from real services."""
    from orbitwatch.validation.loaders import load_gp, load_k_index, load_satcat, load_solar_indices

    gp = load_gp()
    assert len(gp) > 0, "GP loader returned empty DataFrame"
    assert "NORAD_CAT_ID" in gp.columns

    ki = load_k_index()
    assert len(ki) > 0
    assert "kp_index" in ki.columns

    sol = load_solar_indices()
    assert len(sol) > 0

    sat = load_satcat()
    assert len(sat) > 0
    assert "NORAD_CAT_ID" in sat.columns


@pytest.mark.skipif(
    not _postgres_reachable(),
    reason="Postgres not reachable — skipping reject path test",
)
def test_reject_path_idempotent(tmp_path):
    """
    Test 3: Reject path writers.
    Pushes rejected rows through the SAME writer functions run_validation.py uses:
      - _write_rejected_csv
      - _write_dead_letter
      - _write_audit
    Uses dataset name 'test' / source_name 'validation:test' and a temp error path.
    Asserts that running twice does not duplicate dead_letter rows.
    Cleans up afterwards.
    """
    import datetime
    import uuid
    from sqlalchemy import text
    from orbitwatch.common.db import get_postgres_engine
    from scripts.run_validation import _write_rejected_csv, _write_dead_letter, _write_audit

    engine = get_postgres_engine("etl")
    test_dataset = "test"
    test_source_name = "validation:test"

    rej_df = pd.DataFrame([
        {
            "norad_cat_id": 99991,
            "epoch": "2099-01-01T00:00:00",
            "reason_code": "FUTURE_EPOCH",
            "reason_detail": "Epoch is in the future",
        },
        {
            "norad_cat_id": 99992,
            "epoch": "2020-01-01T00:00:00",
            "reason_code": "INVALID_MEAN_MOTION",
            "reason_detail": "Mean motion must be > 0",
        },
    ])

    try:
        # Run 1
        run_id_1 = str(uuid.uuid4())
        started_1 = datetime.datetime.now(datetime.timezone.utc)

        csv_path_1 = _write_rejected_csv(rej_df, test_dataset, errors_dir=tmp_path)
        assert csv_path_1.exists()
        csv_df = pd.read_csv(csv_path_1)
        assert len(csv_df) == 2

        _write_dead_letter(rej_df, test_dataset, run_id_1, source_name=test_source_name)
        _write_audit(
            test_dataset,
            run_id_1,
            rows_in=10,
            rows_out=8,
            rows_rejected=2,
            status="success",
            started_at=started_1,
            clean_table="staging.test_clean",
            source_name=test_source_name,
        )

        with engine.connect() as conn:
            cnt_1 = conn.execute(
                text("SELECT count(*) FROM quality.dead_letter WHERE source_name = :src"),
                {"src": test_source_name},
            ).scalar()
            assert cnt_1 == 2, f"Expected 2 dead letter rows after run 1, got {cnt_1}"

        # Run 2: same data, new run_id
        run_id_2 = str(uuid.uuid4())
        started_2 = datetime.datetime.now(datetime.timezone.utc)

        csv_path_2 = _write_rejected_csv(rej_df, test_dataset, errors_dir=tmp_path)
        assert csv_path_2.exists()

        _write_dead_letter(rej_df, test_dataset, run_id_2, source_name=test_source_name)
        _write_audit(
            test_dataset,
            run_id_2,
            rows_in=10,
            rows_out=8,
            rows_rejected=2,
            status="success",
            started_at=started_2,
            clean_table="staging.test_clean",
            source_name=test_source_name,
        )

        with engine.connect() as conn:
            cnt_2 = conn.execute(
                text("SELECT count(*) FROM quality.dead_letter WHERE source_name = :src"),
                {"src": test_source_name},
            ).scalar()
            # MUST remain 2, NOT duplicate to 4
            assert cnt_2 == 2, f"Expected 2 dead letter rows after run 2 (idempotent), got {cnt_2}"

            # Verify both audit pipeline runs were recorded
            audit_cnt = conn.execute(
                text("SELECT count(*) FROM audit.pipeline_runs WHERE pipeline_name = 'validation_test'"),
            ).scalar()
            assert audit_cnt >= 2, f"Expected at least 2 audit runs, got {audit_cnt}"

    finally:
        # Clean up test rows in quality.dead_letter, audit.pipeline_runs, audit.data_lineage
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM quality.dead_letter WHERE source_name = :src"),
                {"src": test_source_name},
            )
            conn.execute(
                text(
                    "DELETE FROM audit.data_lineage WHERE run_id IN "
                    "(SELECT run_id FROM audit.pipeline_runs WHERE pipeline_name = 'validation_test')"
                ),
            )
            conn.execute(
                text("DELETE FROM audit.pipeline_runs WHERE pipeline_name = 'validation_test'"),
            )
        # Temp dir tmp_path is automatically cleaned up by pytest

