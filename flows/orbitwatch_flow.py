"""
ORBITWATCH – flows/orbitwatch_flow.py
Phase 7: End-to-End Orchestration Flow using Prefect.

Sequential tasks:
  1. download_raw_data: Downloads raw files (Phase 2 ingestion) with retries.
  2. run_data_validation: Executes Great Expectations validation (scripts/run_validation.py).
  3. load_data_warehouse: Executes warehouse load into dw schema (scripts/load_warehouse.py).

If any task fails, downstream tasks are not executed.
Provides local execution when run directly, plus a defined daily schedule (not started automatically).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from prefect import flow, task
from prefect.client.schemas.schedules import CronSchedule

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# ── Daily Schedule Definition (Defined in code, NOT started automatically) ─────
DAILY_SCHEDULE = CronSchedule(cron="0 2 * * *", timezone="UTC")


def _env() -> dict[str, str]:
    """Build environment dictionary with project root and src on PYTHONPATH."""
    env = os.environ.copy()
    current_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{ROOT};{ROOT / 'src'};{current_pp}".rstrip(";")
    return env


# ── Tasks ─────────────────────────────────────────────────────────────────────

@task(
    name="download_raw_data",
    description="Download raw astronomical and solar data with retries",
    retries=2,
    retry_delay_seconds=2,
)
def download_raw_data_task() -> str:
    """Download raw samples using Phase 2 ingestion code."""
    # Check for forced failure injection (for testing error handling)
    if os.environ.get("FAIL_DOWNLOAD_TASK", "").lower() in ("1", "true", "yes"):
        raise RuntimeError("Injected failure: download endpoint unreachable (test condition).")

    download_script = ROOT / "src" / "orbitwatch" / "ingestion" / "download_samples.py"
    cmd = [sys.executable, str(download_script)]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=_env())
    if res.returncode != 0:
        raise RuntimeError(f"Download failed with exit code {res.returncode}:\n{res.stderr}")
    return "Raw data download completed successfully."


@task(
    name="run_data_validation",
    description="Run Great Expectations validation suites across all staging datasets",
)
def run_data_validation_task() -> str:
    """Run Phase 5 Great Expectations validation runner."""
    val_script = ROOT / "scripts" / "run_validation.py"
    cmd = [sys.executable, str(val_script), "--dataset", "all"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=_env())
    if res.returncode != 0:
        raise RuntimeError(f"Validation failed with exit code {res.returncode}:\n{res.stderr}\n{res.stdout}")
    return "Data validation completed successfully with all clean suites passing."


@task(
    name="load_data_warehouse",
    description="Load dimensional star schema in schema dw",
)
def load_data_warehouse_task() -> str:
    """Run Phase 6 dimensional warehouse loader."""
    load_script = ROOT / "scripts" / "load_warehouse.py"
    cmd = [sys.executable, str(load_script)]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=_env())
    if res.returncode != 0:
        raise RuntimeError(f"Warehouse load failed with exit code {res.returncode}:\n{res.stderr}")
    return "Warehouse load completed successfully."


# ── Flow ──────────────────────────────────────────────────────────────────────

@flow(
    name="orbitwatch_pipeline",
    description="ORBITWATCH End-to-End Orchestration Flow (Ingest -> Validate -> Warehouse)",
)
def orbitwatch_pipeline() -> dict[str, Any]:
    """Execute download, validation, and warehouse load in strict sequence."""
    download_res = download_raw_data_task()
    val_res = run_data_validation_task()
    dw_res = load_data_warehouse_task()
    return {
        "download": download_res,
        "validation": val_res,
        "warehouse": dw_res,
    }


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  ORBITWATCH PREFECT ORCHESTRATION PIPELINE")
    print(f"  Schedule in code: {DAILY_SCHEDULE}")
    print("=" * 60 + "\n")
    state = orbitwatch_pipeline(return_state=True)
    print(f"\nFinal Flow State: {state.name}")
    print(f"Flow Result: {state.result()}")
