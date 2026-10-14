"""
ORBITWATCH – src/orbitwatch/validation/loaders.py
Phase 5: Functions that load raw data into pandas DataFrames for validation.

Sources:
  - gp, k_index, solar_indices: read from staging.*_raw (PostgreSQL), payload jsonb flattened.
  - satcat: read from MongoDB raw_satcat collection, payload field flattened.

Raw stores are NEVER modified.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

import pandas as pd
from sqlalchemy import text

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from orbitwatch.common.db import get_mongo_client, get_postgres_engine
from config.settings import get_settings


# ---------------------------------------------------------------------------
# PostgreSQL staging loaders (gp, k_index, solar_indices)
# ---------------------------------------------------------------------------

def _load_staging(table: str, chunk_size: int = 5000) -> pd.DataFrame:
    """
    Generic helper: reads all rows from staging.<table>, flattens the
    JSONB payload column into top-level columns, and returns a DataFrame.

    The staging row metadata columns (event_id, natural_key, mongo_batch_id,
    kafka_topic, kafka_partition, kafka_offset, produced_at, loaded_at) are
    dropped – validation only cares about the payload content.
    """
    engine = get_postgres_engine("etl")
    query = f"SELECT payload FROM staging.{table}"  # nosec – table is a literal in this module
    chunks: list[pd.DataFrame] = []
    with engine.connect() as conn:
        # Stream in chunks to avoid loading all 19k GP rows at once
        result = conn.execution_options(stream_results=True).execute(text(query))
        while True:
            rows = result.fetchmany(chunk_size)
            if not rows:
                break
            # Each row has one column: payload (dict from psycopg jsonb)
            records = [r[0] for r in rows]
            chunks.append(pd.DataFrame(records))
    df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    return df


def load_gp() -> pd.DataFrame:
    """
    Load GP orbital elements from staging.gp_raw.

    Returns a DataFrame with the raw payload columns (e.g. NORAD_CAT_ID,
    EPOCH, INCLINATION, ECCENTRICITY, MEAN_MOTION …).  Column names are
    uppercase as stored in CelesTrak JSON – the cleaning step normalises them.
    """
    return _load_staging("gp_raw")


def load_k_index() -> pd.DataFrame:
    """
    Load NOAA K-index data from staging.k_index_raw.

    Returns a DataFrame with columns: time_tag, kp, kp_index, estimated_kp.
    """
    return _load_staging("k_index_raw")


def load_solar_indices() -> pd.DataFrame:
    """
    Load NOAA solar indices from staging.solar_indices_raw.

    Returns a DataFrame with columns: time-tag, f10.7, ssn, smoothed_ssn, etc.
    The hyphenated column names are kept as-is here; cleaning normalises them.
    """
    return _load_staging("solar_indices_raw")


# ---------------------------------------------------------------------------
# MongoDB loader (satcat)
# ---------------------------------------------------------------------------

def load_satcat(batch_size: int = 2000) -> pd.DataFrame:
    """
    Load SATCAT data from MongoDB raw_satcat collection.

    Each document has a 'payload' field which is a dict of the original CSV
    columns.  We flatten that dict into a DataFrame row, ignoring Mongo
    metadata fields (_id, batch_id, natural_key, payload_hash, loaded_at).

    Returns a DataFrame with uppercase SATCAT columns (NORAD_CAT_ID,
    OBJECT_NAME, OBJECT_TYPE, LAUNCH_DATE, DECAY_DATE, APOGEE, PERIGEE …).
    """
    settings = get_settings()
    client = get_mongo_client()
    db = client[settings.mongo_db]
    collection = db["raw_satcat"]

    records: list[dict] = []
    cursor = collection.find({}, {"payload": 1, "_id": 0}, batch_size=batch_size)
    for doc in cursor:
        payload = doc.get("payload", {})
        records.append(payload)

    client.close()
    return pd.DataFrame(records) if records else pd.DataFrame()
