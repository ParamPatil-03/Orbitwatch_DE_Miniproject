"""
ORBITWATCH – src/orbitwatch/validation/suites.py
Phase 5: Great Expectations 1.x expectation suites for all four datasets.

Two suites per dataset:
  - RAW suite: run on loaded (lightly coerced) data; failures are FINDINGS.
  - CLEAN suite: run after Phase 2 cleaning; must pass for the pipeline to succeed.

GX 1.x API used throughout (ephemeral context, pandas data source,
dataframe asset, batch definition, ExpectationSuite, ValidationDefinition).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import great_expectations as gx
import pandas as pd
from great_expectations import ExpectationSuite
from great_expectations.expectations import (
    ExpectColumnDistinctValuesToBeInSet,
    ExpectColumnPairValuesAToBeGreaterThanB,
    ExpectColumnValuesToBeBetween,
    ExpectColumnValuesToBeInSet,
    ExpectColumnValuesToBeUnique,
    ExpectColumnValuesToNotBeNull,
    ExpectCompoundColumnsToBeUnique,
    ExpectColumnValuesToMatchStrftimeFormat,
)

# ---------------------------------------------------------------------------
# Known value sets – used in RAW and CLEAN suites
# ---------------------------------------------------------------------------

KNOWN_OBJECT_TYPES = ["PAY", "R/B", "DEB", "UNK", "pay", "r/b", "deb", "unk", ""]
KNOWN_ORBIT_REGIMES = ["LEO", "MEO", "GEO", "HEO", "UNKNOWN"]


def _ensure_context() -> gx.AbstractDataContext:
    """Ensure an active GX ephemeral context is present for suite definition."""
    try:
        return gx.get_context()
    except Exception:
        return gx.get_context(mode="ephemeral")


# Initialize context on module load so Expectations can be constructed safely
_ensure_context()


# ---------------------------------------------------------------------------
# Suite builders
# ---------------------------------------------------------------------------

def build_gp_raw_suite() -> ExpectationSuite:
    """
    RAW suite for GP data (expectations on the payload columns before cleaning).
    Column names are uppercase as stored in CelesTrak JSON.
    """
    _ensure_context()
    suite = ExpectationSuite(name="gp_raw_suite")

    # NORAD_CAT_ID not null
    suite.add_expectation(
        ExpectColumnValuesToNotBeNull(column="NORAD_CAT_ID", mostly=1.0)
    )
    # INCLINATION between 0 and 180
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="INCLINATION", min_value=0.0, max_value=180.0, mostly=1.0
        )
    )
    # ECCENTRICITY >= 0 and < 1
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="ECCENTRICITY", min_value=0.0, max_value=0.9999999, mostly=1.0
        )
    )
    # MEAN_MOTION > 0 (GX between uses inclusive bounds, so min=1e-9 as a proxy)
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="MEAN_MOTION", min_value=1e-9, mostly=1.0
        )
    )
    # EPOCH not null and not in future
    suite.add_expectation(
        ExpectColumnValuesToNotBeNull(column="EPOCH", mostly=1.0)
    )
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="EPOCH", max_value=datetime.now(timezone.utc), mostly=1.0
        )
    )
    # Compound uniqueness (NORAD_CAT_ID, EPOCH)
    suite.add_expectation(
        ExpectCompoundColumnsToBeUnique(
            column_list=["NORAD_CAT_ID", "EPOCH"], mostly=1.0
        )
    )
    return suite


def build_gp_clean_suite() -> ExpectationSuite:
    """
    CLEAN suite for GP data (after Phase 2 cleaning; must pass entirely).
    Column names are lowercase (cleaning normalises them).
    """
    suite = ExpectationSuite(name="gp_clean_suite")

    suite.add_expectation(ExpectColumnValuesToNotBeNull(column="norad_cat_id"))
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(column="inclination", min_value=0.0, max_value=180.0)
    )
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(column="eccentricity", min_value=0.0, max_value=0.9999999)
    )
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(column="mean_motion", min_value=1e-9)
    )
    suite.add_expectation(ExpectColumnValuesToNotBeNull(column="epoch"))
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(column="epoch", max_value=datetime.now(timezone.utc))
    )
    suite.add_expectation(
        ExpectCompoundColumnsToBeUnique(column_list=["norad_cat_id", "epoch"])
    )
    # orbit_regime must be in the allowed set
    suite.add_expectation(
        ExpectColumnValuesToBeInSet(
            column="orbit_regime", value_set=KNOWN_ORBIT_REGIMES
        )
    )
    return suite


def build_satcat_raw_suite() -> ExpectationSuite:
    """RAW suite for SATCAT (uppercase column names from CelesTrak CSV)."""
    suite = ExpectationSuite(name="satcat_raw_suite")

    suite.add_expectation(
        ExpectColumnValuesToNotBeNull(column="NORAD_CAT_ID", mostly=1.0)
    )
    suite.add_expectation(
        ExpectColumnValuesToBeUnique(column="NORAD_CAT_ID", mostly=1.0)
    )
    suite.add_expectation(
        ExpectColumnValuesToBeInSet(
            column="OBJECT_TYPE",
            value_set=KNOWN_OBJECT_TYPES,
            mostly=1.0,
        )
    )
    # perigee <= apogee where both exist – checked by pair values
    suite.add_expectation(
        ExpectColumnPairValuesAToBeGreaterThanB(
            column_A="APOGEE",
            column_B="PERIGEE",
            or_equal=True,
            ignore_row_if="either_value_is_missing",
            mostly=1.0,
        )
    )
    # launch_date not in future (where not null)
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="LAUNCH_DATE", max_value=datetime.now(timezone.utc), mostly=1.0
        )
    )
    # decay_date not before launch_date (where both exist; null decay_date is allowed)
    suite.add_expectation(
        ExpectColumnPairValuesAToBeGreaterThanB(
            column_A="DECAY_DATE",
            column_B="LAUNCH_DATE",
            or_equal=True,
            ignore_row_if="either_value_is_missing",
            mostly=1.0,
        )
    )
    # null DECAY_DATE is ALLOWED – no not-null expectation for it
    return suite


def build_satcat_clean_suite() -> ExpectationSuite:
    """CLEAN suite for SATCAT (lowercase column names after cleaning)."""
    suite = ExpectationSuite(name="satcat_clean_suite")

    suite.add_expectation(ExpectColumnValuesToNotBeNull(column="norad_cat_id"))
    suite.add_expectation(ExpectColumnValuesToBeUnique(column="norad_cat_id"))
    suite.add_expectation(
        ExpectColumnValuesToBeInSet(
            column="object_type",
            value_set=[v for v in KNOWN_OBJECT_TYPES if v],
        )
    )
    suite.add_expectation(
        ExpectColumnPairValuesAToBeGreaterThanB(
            column_A="apogee",
            column_B="perigee",
            or_equal=True,
            ignore_row_if="either_value_is_missing",
            mostly=1.0,
        )
    )
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="launch_date", max_value=datetime.now(timezone.utc)
        )
    )
    suite.add_expectation(
        ExpectColumnPairValuesAToBeGreaterThanB(
            column_A="decay_date",
            column_B="launch_date",
            or_equal=True,
            ignore_row_if="either_value_is_missing",
            mostly=1.0,
        )
    )
    suite.add_expectation(
        ExpectColumnValuesToBeInSet(
            column="orbit_regime", value_set=KNOWN_ORBIT_REGIMES
        )
    )
    return suite


def build_k_index_raw_suite() -> ExpectationSuite:
    """RAW suite for K-index data."""
    suite = ExpectationSuite(name="k_index_raw_suite")

    suite.add_expectation(
        ExpectColumnValuesToNotBeNull(column="time_tag", mostly=1.0)
    )
    suite.add_expectation(
        ExpectColumnValuesToBeUnique(column="time_tag", mostly=1.0)
    )
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="kp_index", min_value=0.0, max_value=9.0, mostly=1.0
        )
    )
    return suite


def build_k_index_clean_suite() -> ExpectationSuite:
    """CLEAN suite for K-index data."""
    suite = ExpectationSuite(name="k_index_clean_suite")

    suite.add_expectation(ExpectColumnValuesToNotBeNull(column="time_tag"))
    suite.add_expectation(ExpectColumnValuesToBeUnique(column="time_tag"))
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(column="kp_index", min_value=0.0, max_value=9.0)
    )
    return suite


def build_solar_raw_suite() -> ExpectationSuite:
    """
    RAW suite for solar indices.
    NOTE: the time field is named 'time-tag' (with a hyphen) in the raw payload.
    f10.7 uses the literal column name from the payload.
    """
    suite = ExpectationSuite(name="solar_raw_suite")

    # Simple approach: validate on the normalised column names that the
    # loader already returns (time-tag, f10.7, ssn).
    # We rename tricky columns for GX in the runner before passing the df.
    suite.add_expectation(
        ExpectColumnValuesToNotBeNull(column="time_tag", mostly=1.0)
    )
    suite.add_expectation(
        ExpectColumnValuesToBeUnique(column="time_tag", mostly=1.0)
    )
    # f10.7 >= 0 where not null  (GX skips nulls by default with mostly)
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="f107", min_value=0.0, mostly=0.95  # -1 sentinel is converted to NaN by cleaning
        )
    )
    # ssn >= 0 where not null
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(
            column="ssn", min_value=0.0, mostly=0.95
        )
    )
    return suite


def build_solar_clean_suite() -> ExpectationSuite:
    """CLEAN suite for solar indices."""
    suite = ExpectationSuite(name="solar_clean_suite")

    suite.add_expectation(ExpectColumnValuesToNotBeNull(column="time_tag"))
    suite.add_expectation(ExpectColumnValuesToBeUnique(column="time_tag"))
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(column="f107", min_value=0.0, mostly=0.95)
    )
    suite.add_expectation(
        ExpectColumnValuesToBeBetween(column="ssn", min_value=0.0, mostly=0.95)
    )
    return suite


# ---------------------------------------------------------------------------
# Runner helper
# ---------------------------------------------------------------------------

def run_suite(
    suite: ExpectationSuite,
    df: pd.DataFrame,
    context: gx.AbstractDataContext | None = None,
) -> gx.core.expectation_validation_result.ExpectationSuiteValidationResult:
    """
    Run an ExpectationSuite against a DataFrame using GX 1.x ephemeral context.

    Args:
        suite:   The suite to run.
        df:      The DataFrame to validate.
        context: An existing GX context (reuse to avoid recreating for each suite).

    Returns:
        The validation result object.
    """
    import uuid

    # Use provided context or create ephemeral one
    ctx = context or _ensure_context()

    uid = f"{suite.name}_{uuid.uuid4().hex[:8]}"
    ds = ctx.data_sources.add_pandas(f"ds_{uid}")
    da = ds.add_dataframe_asset(f"asset_{uid}")
    bd = da.add_batch_definition_whole_dataframe(f"batch_{uid}")

    suite_obj = ctx.suites.add_or_update(suite)

    vd = ctx.validation_definitions.add_or_update(
        gx.ValidationDefinition(name=f"vd_{uid}", data=bd, suite=suite_obj)
    )
    result = vd.run(batch_parameters={"dataframe": df})
    return result
