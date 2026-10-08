"""
Bulk loader for ORBITWATCH raw data.
Reads files in data/raw/ and sends them to the ingestion API in chunks.
"""
import os
import csv
import json
import argparse
import requests
from pathlib import Path

import sys
sys.path.insert(0, str((Path(__file__).parent.parent / "src").resolve()))
sys.path.insert(0, str((Path(__file__).parent.parent).resolve()))

from config.settings import get_settings

def chunked(iterable, n):
    """Yield successive n-sized chunks from iterable."""
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == n:
            yield chunk
            chunk = []
    if chunk:
        yield chunk

def load_json(filepath, source):
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def load_csv(filepath, source):
    data = []
    with open(filepath, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        basename = os.path.basename(filepath)
        for row in reader:
            if "gp_" in basename and "debris" in basename:
                # Add source_group, e.g. gp_cosmos_1408_debris
                source_group = "_".join(basename.split("_")[:-1]) 
                row["source_group"] = source_group
            data.append(row)
    return data
    
def send_to_api(records, source, api_key):
    headers = {"X-API-Key": api_key}
    url = f"http://localhost:8000/ingest/{source}"
    resp = requests.post(url, json=records, headers=headers)
    if resp.status_code != 200:
        print(f"Error sending chunk: {resp.status_code} - {resp.text}")
    resp.raise_for_status()
    return resp.json()

def process_file(filepath, source, api_key):
    print(f"Processing {filepath} for source {source}")
    if filepath.endswith('.json'):
        records = load_json(filepath, source)
    else:
        records = load_csv(filepath, source)
        
    total_received = 0
    total_inserted = 0
    total_duplicates = 0
    total_rejected = 0
    
    for chunk in chunked(records, 2000):
        res = send_to_api(chunk, source, api_key)
        total_received += res["received"]
        total_inserted += res["inserted"]
        total_duplicates += res["duplicates"]
        total_rejected += res["rejected"]
        print(f"  Chunk: {res['inserted']} inserted, {res['duplicates']} dups, {res['rejected']} rej")
        
    print(f"Done {source}: Received={total_received}, Inserted={total_inserted}, Duplicates={total_duplicates}, Rejected={total_rejected}\n")

def main():
    parser = argparse.ArgumentParser(description="Bulk load raw files to MongoDB via API")
    args = parser.parse_args()
    
    settings = get_settings()
    api_key = settings.api_key
    
    raw_dir = Path("data/raw")
    if not raw_dir.exists():
        print("data/raw directory not found.")
        return
        
    file_mappings = [
        ("satcat_*.csv", "satcat"),
        ("gp_*.csv", "gp"),
        ("k_index_*.json", "k_index"),
        ("solar_indices_*.json", "solar_indices")
    ]
    
    for pattern, source in file_mappings:
        for filepath in raw_dir.glob(pattern):
            process_file(str(filepath), source, api_key)

if __name__ == "__main__":
    main()
