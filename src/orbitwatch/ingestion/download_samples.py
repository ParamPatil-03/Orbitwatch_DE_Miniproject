"""
ORBITWATCH – src/orbitwatch/ingestion/download_samples.py
Downloads sample data from CelesTrak and NOAA SWPC.
Saves to data/raw/ with a timestamp. Skips if already exists today unless --force is used.
"""

import argparse
import datetime
import os
import time
from pathlib import Path

import requests

from orbitwatch.common.logging_setup import get_logger

logger = get_logger("download_samples")

HEADERS = {"User-Agent": "ORBITWATCH-student-project/1.0"}

URLS = {
    "satcat": "https://celestrak.org/pub/satcat.csv",
    "gp_active": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=csv",
    "gp_cosmos_2251_debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-2251-debris&FORMAT=csv",
    "gp_iridium_33_debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-33-debris&FORMAT=csv",
    "gp_fengyun_1c_debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=fengyun-1c-debris&FORMAT=csv",
    "gp_cosmos_1408_debris": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cosmos-1408-debris&FORMAT=csv",
    "k_index": "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json",
    "solar_indices": "https://services.swpc.noaa.gov/json/solar-cycle/observed-solar-cycle-indices.json"
}

def download_file(name: str, url: str, raw_dir: Path, force: bool = False) -> Path | None:
    """Download a file with retries and return the path."""
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    extension = "csv" if "csv" in url.lower() or "gp.php" in url.lower() else "json"
    filename = f"{name}_{today}.{extension}"
    filepath = raw_dir / filename

    if filepath.exists() and not force:
        logger.info(f"Skipping {name}, {filename} already exists. Use --force to override.")
        return filepath

    logger.info(f"Downloading {name} from {url}...")
    
    for attempt in range(1, 4):
        try:
            start_time = time.time()
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            
            with open(filepath, "wb") as f:
                f.write(response.content)
                
            elapsed = time.time() - start_time
            size_kb = len(response.content) / 1024
            
            # Simple row count (approximate for JSON, exact for CSV if we count newlines)
            if extension == "csv":
                row_count = response.text.count('\n')
            else:
                row_count = response.text.count('{')  # rough estimate of JSON objects
                
            logger.info(f"SUCCESS: {filename} | Size: {size_kb:.1f} KB | Rows: {row_count} | Time: {elapsed:.2f}s")
            return filepath
            
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt} failed for {name}: {e}")
            if attempt < 3:
                time.sleep(2 ** attempt)
            else:
                logger.error(f"FAILED to download {name} after 3 attempts.")
                return None

def main():
    parser = argparse.ArgumentParser(description="Download OrbitWatch sample data")
    parser.add_argument("--force", action="store_true", help="Force download even if file exists")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent.parent
    raw_dir = project_root / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for name, url in URLS.items():
        download_file(name, url, raw_dir, args.force)

if __name__ == "__main__":
    main()
