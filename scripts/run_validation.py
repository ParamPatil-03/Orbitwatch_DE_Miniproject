#!/usr/bin/env python3
"""
ORBITWATCH – scripts/run_validation.py
Phase 5: Validation runner.

Flow per dataset:
  1. Load raw data (from staging tables or MongoDB).
  2. Run RAW GX suite  → findings (failures logged, exit code unaffected).
  3. Clean with Phase 2 functions.
  4. Run CLEAN GX suite → gate (all must pass, else exit code 1).
  5. Write clean rows to staging.*_clean (TRUNCATE + INSERT in a transaction).
  6. Write rejected rows to data/errors/rejected_<dataset>.csv.
  7. Insert rejected rows into quality.dead_letter (delete previous for source first).
  8. Write audit rows: pipeline_runs + data_lineage.
  9. Build GX Data Docs HTML and copy index.html to docs/validation_report/.

Exit code 0 if all CLEAN suites pass, else 1.

Usage:
  python scripts/run_validation.py [--dataset gp|k_index|solar_indices|satcat|all]
  python scripts/run_validation.py --demo-bad-batch
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import sys
import traceback
import uuid
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# ── Path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# Suppress noisy GX progress bars unless debugging
os.environ.setdefault("GX_ANALYTICS_ENABLED", "false")
warnings.filterwarnings("ignore", category=DeprecationWarning)

import great_expectations as gx

from orbitwatch.common.db import get_mongo_client, get_postgres_engine
from orbitwatch.etl.cleaning import (
    clean_gp,
    clean_k_index,
    clean_satcat,
    clean_solar_indices,
)
from orbitwatch.validation.loaders import (
    load_gp,
    load_k_index,
    load_satcat,
    load_solar_indices,
)
from orbitwatch.validation.suites import (
    build_gp_clean_suite,
    build_gp_raw_suite,
    build_k_index_clean_suite,
    build_k_index_raw_suite,
    build_satcat_clean_suite,
    build_satcat_raw_suite,
    build_solar_clean_suite,
    build_solar_raw_suite,
)
from config.settings import get_settings


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ERRORS_DIR = ROOT / "data" / "errors"
VALIDATION_REPORT_DIR = ROOT / "docs" / "validation_report"
GX_DIR = ROOT / "gx"

DATASETS = ["gp", "k_index", "solar_indices", "satcat"]

# Map dataset -> (raw_suite_fn, clean_suite_fn, clean_table, load_fn, clean_fn)
DATASET_CONFIG = {
    "gp": {
        "load": load_gp,
        "clean": clean_gp,
        "raw_suite": build_gp_raw_suite,
        "clean_suite": build_gp_clean_suite,
        "clean_table": "staging.gp_clean",
        "source_name": "staging.gp_raw",
    },
    "k_index": {
        "load": load_k_index,
        "clean": clean_k_index,
        "raw_suite": build_k_index_raw_suite,
        "clean_suite": build_k_index_clean_suite,
        "clean_table": "staging.k_index_clean",
        "source_name": "staging.k_index_raw",
    },
    "solar_indices": {
        "load": load_solar_indices,
        "clean": clean_solar_indices,
        "raw_suite": build_solar_raw_suite,
        "clean_suite": build_solar_clean_suite,
        "clean_table": "staging.solar_indices_clean",
        "source_name": "staging.solar_indices_raw",
    },
    "satcat": {
        "load": load_satcat,
        "clean": clean_satcat,
        "raw_suite": build_satcat_raw_suite,
        "clean_suite": build_satcat_clean_suite,
        "clean_table": "staging.satcat_clean",
        "source_name": "mongodb.raw_satcat",
    },
}


# ---------------------------------------------------------------------------
# GX context (file-backed for Data Docs generation)
# ---------------------------------------------------------------------------

def get_gx_context() -> gx.AbstractDataContext:
    """
    Return a file-backed GX context rooted at gx/.
    Creates the directory structure if it does not exist.
    """
    GX_DIR.mkdir(exist_ok=True)
    try:
        ctx = gx.get_context(project_root_dir=str(GX_DIR), mode="file")
    except Exception:
        # If no existing project, initialise one
        ctx = gx.get_context(mode="file", project_root_dir=str(GX_DIR))
    return ctx


# ---------------------------------------------------------------------------
# Pre-processing helpers
# ---------------------------------------------------------------------------

def _prep_gp(df: pd.DataFrame) -> pd.DataFrame:
    """Light coercion for the RAW GP suite (columns stay uppercase)."""
    df = df.copy()
    for col in ["INCLINATION", "ECCENTRICITY", "MEAN_MOTION"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "EPOCH" in df.columns:
        df["EPOCH"] = pd.to_datetime(df["EPOCH"], errors="coerce", utc=True)
    return df


def _prep_solar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename hyphenated solar columns for GX compatibility.
    'time-tag' -> 'time_tag', 'f10.7' -> 'f107'.
    """
    df = df.copy()
    rename = {}
    if "time-tag" in df.columns:
        rename["time-tag"] = "time_tag"
    if "f10.7" in df.columns:
        rename["f10.7"] = "f107"
    if rename:
        df = df.rename(columns=rename)
    for col in ["f107", "ssn"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df.loc[df[col] == -1, col] = np.nan
    return df


def _prep_k_index(df: pd.DataFrame) -> pd.DataFrame:
    """Light coercion for the RAW K-index suite."""
    df = df.copy()
    if "kp_index" in df.columns:
        df["kp_index"] = pd.to_numeric(df["kp_index"], errors="coerce")
    return df


def _prep_satcat(df: pd.DataFrame) -> pd.DataFrame:
    """Light coercion for the RAW SATCAT suite."""
    df = df.copy()
    for col in ["APOGEE", "PERIGEE"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "LAUNCH_DATE" in df.columns:
        df["LAUNCH_DATE"] = pd.to_datetime(df["LAUNCH_DATE"], errors="coerce", utc=True)
    if "DECAY_DATE" in df.columns:
        df["DECAY_DATE"] = pd.to_datetime(df["DECAY_DATE"], errors="coerce", utc=True)
    return df


PREP_FN = {
    "gp": _prep_gp,
    "k_index": _prep_k_index,
    "solar_indices": _prep_solar,
    "satcat": _prep_satcat,
}


# ---------------------------------------------------------------------------
# Suite runner (using the shared GX context)
# ---------------------------------------------------------------------------

def _run_suite(
    ctx: gx.AbstractDataContext,
    suite: gx.ExpectationSuite,
    df: pd.DataFrame,
) -> gx.core.expectation_validation_result.ExpectationSuiteValidationResult:
    """Run a GX 1.x suite against df using the given context."""
    uid = str(uuid.uuid4())[:8]
    ds_name = f"ds_{uid}"
    asset_name = f"asset_{uid}"
    batch_name = f"batch_{uid}"
    vd_name = f"vd_{uid}"

    ds = ctx.data_sources.add_pandas(ds_name)
    da = ds.add_dataframe_asset(asset_name)
    bd = da.add_batch_definition_whole_dataframe(batch_name)
    suite_obj = ctx.suites.add_or_update(suite)

    vd = ctx.validation_definitions.add_or_update(
        gx.ValidationDefinition(name=vd_name, data=bd, suite=suite_obj)
    )
    result = vd.run(batch_parameters={"dataframe": df})
    return result


def _summarise_result(result) -> tuple[bool, list[dict]]:
    """Return (passed, list_of_failed_expectations_with_counts)."""
    failed = []
    for r in result.results:
        if not r.success:
            exp_type = r.expectation_config.type
            kwargs = r.expectation_config.kwargs or {}
            col = kwargs.get("column") or kwargs.get("column_list") or kwargs.get("column_A") or ""
            exp_desc = f"{exp_type} [{col}]" if col else exp_type
            unexpected = r.result.get("unexpected_count", "?")
            failed.append({
                "expectation": exp_desc,
                "type": exp_type,
                "column": str(col),
                "unexpected_count": unexpected,
            })
    return result.success, failed


# ---------------------------------------------------------------------------
# DB writers
# ---------------------------------------------------------------------------

def _write_clean_table(df: pd.DataFrame, table: str) -> int:
    """
    TRUNCATE + INSERT clean rows inside a single transaction.
    Returns the number of rows written.
    """
    if df.empty:
        return 0
    engine = get_postgres_engine("etl")
    schema, tbl = table.split(".")
    df_out = df.copy()
    # Drop internal-only columns that are not in the clean table
    for drop_col in ["reason_code", "reason_detail", "loaded_at"]:
        if drop_col in df_out.columns:
            df_out = df_out.drop(columns=[drop_col])
    df_out["loaded_at"] = datetime.datetime.now(datetime.timezone.utc)
    with engine.begin() as conn:
        cols_res = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :tbl"
            ),
            {"schema": schema, "tbl": tbl},
        )
        existing_cols = {r[0] for r in cols_res}
        keep_cols = [c for c in df_out.columns if c in existing_cols]
        df_out = df_out[keep_cols]
        conn.execute(text(f"TRUNCATE TABLE {schema}.{tbl}"))
        df_out.to_sql(tbl, conn, schema=schema, if_exists="append", index=False)
    return len(df_out)


def _write_rejected_csv(
    rejected_df: pd.DataFrame, dataset: str, errors_dir: Optional[Path] = None
) -> Path:
    """Write rejected rows to data/errors/rejected_<dataset>.csv."""
    out_dir = errors_dir or ERRORS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"rejected_{dataset}.csv"
    if rejected_df.empty:
        # Write empty file with headers so the file always exists
        pd.DataFrame(columns=["reason_code", "reason_detail"]).to_csv(path, index=False)
    else:
        rejected_df.to_csv(path, index=False)
    return path


def _write_dead_letter(
    rejected_df: pd.DataFrame,
    dataset: str,
    run_id: str,
    source_name: Optional[str] = None,
) -> None:
    """
    Delete previous quality.dead_letter rows for this dataset, then insert new ones.
    Idempotent: reruns do not accumulate duplicates.
    """
    src = source_name or f"validation:{dataset}"
    engine = get_postgres_engine("etl")
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM quality.dead_letter WHERE source_name = :src"),
            {"src": src},
        )
        if rejected_df.empty:
            return

        for _, row in rejected_df.iterrows():
            import json
            # Build a JSON payload from the row (drop reason columns)
            payload_dict = row.drop(
                labels=[c for c in ["reason_code", "reason_detail"] if c in row.index],
                errors="ignore",
            ).to_dict()
            # Convert non-serialisable types
            for k, v in payload_dict.items():
                if isinstance(v, (pd.Timestamp, datetime.datetime)):
                    payload_dict[k] = str(v)
                elif isinstance(v, float) and np.isnan(v):
                    payload_dict[k] = None
            conn.execute(
                text("""
                    INSERT INTO quality.dead_letter
                        (source_name, payload, reason_code, reason_detail, run_id)
                    VALUES (:src, :payload, :code, :detail, :run_id)
                """),
                {
                    "src": src,
                    "payload": json.dumps(payload_dict),
                    "code": str(row.get("reason_code", "UNKNOWN")),
                    "detail": str(row.get("reason_detail", "")),
                    "run_id": run_id,
                },
            )


def _write_audit(
    dataset: str,
    run_id: str,
    rows_in: int,
    rows_out: int,
    rows_rejected: int,
    status: str,
    started_at: datetime.datetime,
    clean_table: str,
    source_name: Optional[str] = None,
) -> None:
    """Write one pipeline_runs row and one data_lineage row."""
    engine = get_postgres_engine("etl")
    finished_at = datetime.datetime.now(datetime.timezone.utc)
    src = source_name or DATASET_CONFIG.get(dataset, {}).get("source_name", f"staging.{dataset}_raw")
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO audit.pipeline_runs
                    (run_id, pipeline_name, status, rows_in, rows_out, rows_rejected,
                     started_at, finished_at)
                VALUES
                    (:run_id, :name, :status, :rows_in, :rows_out, :rows_rejected,
                     :started_at, :finished_at)
            """),
            {
                "run_id": run_id,
                "name": f"validation_{dataset}",
                "status": status,
                "rows_in": rows_in,
                "rows_out": rows_out,
                "rows_rejected": rows_rejected,
                "started_at": started_at,
                "finished_at": finished_at,
            },
        )
        conn.execute(
            text("""
                INSERT INTO audit.data_lineage
                    (run_id, source_name, target_name, step_name, row_count, recorded_at)
                VALUES
                    (:run_id, :src, :tgt, :step, :count, :ts)
            """),
            {
                "run_id": run_id,
                "src": src,
                "tgt": clean_table,
                "step": f"validation_{dataset}",
                "count": rows_out,
                "ts": finished_at,
            },
        )


# ---------------------------------------------------------------------------
# Data Docs
# ---------------------------------------------------------------------------

def _build_data_docs(ctx: gx.AbstractDataContext) -> None:
    """Build GX HTML Data Docs and copy index.html to docs/validation_report/."""
    try:
        ctx.build_data_docs()
        # Find the generated index.html
        sites = ctx.get_docs_sites_urls()
        src_html: Optional[Path] = None
        for site in sites:
            url = site.get("site_url", "")
            if url.startswith("file://"):
                candidate = Path(url[7:])
                if candidate.exists():
                    src_html = candidate
                    break
        if src_html:
            VALIDATION_REPORT_DIR.mkdir(parents=True, exist_ok=True)
            # Copy the entire data docs directory
            site_dir = src_html.parent
            dest = VALIDATION_REPORT_DIR
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(site_dir, dest)
            print(f"\n[Docs] Validation report copied to {dest / 'index.html'}")
        else:
            print("[Docs] Could not locate Data Docs index.html.")
    except Exception as exc:
        print(f"[Docs] Failed to build Data Docs: {exc}")


# ---------------------------------------------------------------------------
# Per-dataset pipeline
# ---------------------------------------------------------------------------

def run_dataset(
    dataset: str, ctx: gx.AbstractDataContext
) -> tuple[dict, bool]:
    """
    Run the full validation pipeline for one dataset.

    Returns:
        summary_row: dict with dataset stats for the summary table.
        clean_passed: bool — True if the CLEAN suite passed.
    """
    cfg = DATASET_CONFIG[dataset]
    run_id = str(uuid.uuid4())
    started_at = datetime.datetime.now(datetime.timezone.utc)
    status = "failed"  # overwritten in finally if success

    rows_in = rows_out = rows_rejected = 0
    raw_pass = False
    raw_failed: list[dict] = []
    clean_pass = False
    clean_failed: list[dict] = []

    try:
        # ── 1. Load ───────────────────────────────────────────────────────────
        print(f"\n[{dataset}] Loading...")
        raw_df = cfg["load"]()
        rows_in = len(raw_df)
        print(f"[{dataset}] Loaded {rows_in} rows.")

        # ── 2. RAW suite ──────────────────────────────────────────────────────
        print(f"[{dataset}] Running RAW suite...")
        raw_prep = PREP_FN[dataset](raw_df)
        raw_suite = cfg["raw_suite"]()
        raw_result = _run_suite(ctx, raw_suite, raw_prep)
        raw_pass, raw_failed = _summarise_result(raw_result)
        print(f"[{dataset}] RAW suite: {'PASS' if raw_pass else 'FAIL'}, "
              f"{len(raw_failed)} failed expectations.")

        # ── 3. Clean ──────────────────────────────────────────────────────────
        print(f"[{dataset}] Cleaning...")
        clean_df, rejected_df, stats = cfg["clean"](raw_df)
        rows_out = len(clean_df)
        rows_rejected = len(rejected_df)
        print(f"[{dataset}] Clean: {rows_out} rows, {rows_rejected} rejected.")

        # ── 4. CLEAN suite ────────────────────────────────────────────────────
        print(f"[{dataset}] Running CLEAN suite...")
        # Prep clean df for GX (rename any remaining tricky columns)
        clean_prep = PREP_FN[dataset](clean_df) if dataset == "solar_indices" else clean_df.copy()
        # Ensure time_tag is string-comparable for solar
        clean_suite = cfg["clean_suite"]()
        clean_result = _run_suite(ctx, clean_suite, clean_prep)
        clean_pass, clean_failed = _summarise_result(clean_result)
        print(f"[{dataset}] CLEAN suite: {'PASS' if clean_pass else 'FAIL'}, "
              f"{len(clean_failed)} failed expectations.")

        # ── 5. Write clean table ──────────────────────────────────────────────
        written = _write_clean_table(clean_df, cfg["clean_table"])
        print(f"[{dataset}] Wrote {written} rows to {cfg['clean_table']}.")

        # ── 6. Rejected CSV ───────────────────────────────────────────────────
        _write_rejected_csv(rejected_df, dataset)

        # ── 7. Dead letter ────────────────────────────────────────────────────
        _write_dead_letter(rejected_df, dataset, run_id)

        status = "success"

    except Exception as exc:
        print(f"[{dataset}] ERROR: {exc}")
        traceback.print_exc()
        status = "failed"

    finally:
        # ── 8. Audit (always runs, even on failure) ───────────────────────────
        try:
            _write_audit(
                dataset, run_id, rows_in, rows_out, rows_rejected, status, started_at,
                cfg["clean_table"],
            )
        except Exception as audit_exc:
            print(f"[{dataset}] Audit write failed: {audit_exc}")

    summary = {
        "dataset": dataset,
        "rows_in": rows_in,
        "raw_suite": "PASS" if raw_pass else f"FAIL ({len(raw_failed)} expectations)",
        "raw_failed": raw_failed,
        "rows_rejected": rows_rejected,
        "rows_out": rows_out,
        "clean_suite": "PASS" if clean_pass else f"FAIL ({len(clean_failed)} expectations)",
        "status": status,
    }
    return summary, clean_pass


# ---------------------------------------------------------------------------
# Demo bad batch
# ---------------------------------------------------------------------------

def run_demo_bad_batch() -> None:
    """
    DEMO ONLY: Take 50 GP rows from staging, corrupt them, run the RAW suite.
    Never writes to any database or clean table.
    """
    print("\n" + "=" * 60)
    print("  *** DEMO BAD BATCH — no data will be written ***")
    print("=" * 60)

    raw_df = load_gp()
    demo_df = raw_df.head(50).copy()
    demo_df = _prep_gp(demo_df)

    # Inject corrupt values across 5 distinct expectation groups
    demo_df.loc[demo_df.index[:10], "INCLINATION"] = 200.0   # out of range (0-180)
    demo_df.loc[demo_df.index[10:20], "ECCENTRICITY"] = 1.5  # eccentricity >= 1
    demo_df.loc[demo_df.index[20:30], "NORAD_CAT_ID"] = None  # null ID
    demo_df.loc[demo_df.index[30:40], "EPOCH"] = pd.Timestamp("2099-01-01T00:00:00", tz="UTC")  # future epoch
    demo_df.loc[demo_df.index[40:50], "MEAN_MOTION"] = -5.0  # negative (must be > 0)

    print(f"\n[DEMO] 50 rows with injected errors:")
    print("  rows 0-9:   INCLINATION = 200  (should be 0-180)")
    print("  rows 10-19: ECCENTRICITY = 1.5 (must be < 1)")
    print("  rows 20-29: NORAD_CAT_ID = null")
    print("  rows 30-39: EPOCH = 2099 (future)")
    print("  rows 40-49: MEAN_MOTION = -5  (must be > 0)")

    ctx = gx.get_context(mode="ephemeral")
    raw_suite = build_gp_raw_suite()
    result = _run_suite(ctx, raw_suite, demo_df)
    _, failed = _summarise_result(result)

    print(f"\n[DEMO] RAW suite result: {'PASS' if result.success else 'FAIL'}")
    print(f"[DEMO] Failed expectations ({len(failed)}):")
    for f in failed:
        print(f"  - {f['expectation']}: {f['unexpected_count']} unexpected values")

    # Confirm no DB writes
    engine = get_postgres_engine("etl")
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM staging.gp_clean")).scalar()
    print(f"\n[DEMO] staging.gp_clean count (must be unchanged): {count}")
    print("\n[DEMO] DONE — nothing written to database.")


# ---------------------------------------------------------------------------
# Summary table printer
# ---------------------------------------------------------------------------

def _print_summary(summaries: list[dict]) -> None:
    header = f"{'Dataset':<20} {'Rows In':>9} {'RAW Suite':<30} {'Rejected':>9} {'Rows Out':>9} {'CLEAN Suite':<20} {'Status':<8}"
    print("\n" + "=" * len(header))
    print("  VALIDATION SUMMARY")
    print("=" * len(header))
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(
            f"{s['dataset']:<20} {s['rows_in']:>9} {s['raw_suite']:<30} "
            f"{s['rows_rejected']:>9} {s['rows_out']:>9} {s['clean_suite']:<20} {s['status']:<8}"
        )
    print("=" * len(header))

    # Per-dataset RAW findings detail
    for s in summaries:
        if s["raw_failed"]:
            print(f"\n[RAW FINDINGS] {s['dataset']}:")
            for f in s["raw_failed"]:
                print(f"  - {f['expectation']}: {f['unexpected_count']} unexpected rows")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="ORBITWATCH Phase 5 Validation Runner")
    parser.add_argument(
        "--dataset",
        choices=DATASETS + ["all"],
        default="all",
        help="Dataset to validate (default: all)",
    )
    parser.add_argument(
        "--demo-bad-batch",
        action="store_true",
        help="DEMO: corrupt 50 GP rows and run RAW suite only. No DB writes.",
    )
    args = parser.parse_args()

    if args.demo_bad_batch:
        run_demo_bad_batch()
        return 0

    datasets = DATASETS if args.dataset == "all" else [args.dataset]

    # Use a single file-backed GX context for Data Docs generation
    ctx = get_gx_context()

    summaries: list[dict] = []
    all_clean_passed = True

    for ds in datasets:
        summary, clean_passed = run_dataset(ds, ctx)
        summaries.append(summary)
        if not clean_passed:
            all_clean_passed = False

    # Print summary table
    _print_summary(summaries)

    # Build Data Docs
    _build_data_docs(ctx)

    exit_code = 0 if all_clean_passed else 1
    print(f"\nExit code: {exit_code} ({'all CLEAN suites passed' if exit_code == 0 else 'one or more CLEAN suites FAILED'})")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
