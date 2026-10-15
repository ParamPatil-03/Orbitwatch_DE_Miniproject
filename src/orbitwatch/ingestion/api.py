"""
FastAPI ingestion service for ORBITWATCH raw data.
Stores incoming payloads in MongoDB.
"""
import uuid
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import List, Union, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Header, Depends, Request, status, Security, Body
from fastapi.security import APIKeyHeader
from pydantic import ValidationError
from pymongo import MongoClient, IndexModel, ASCENDING
from pymongo.errors import BulkWriteError
from pymongo.operations import InsertOne

from config.settings import get_settings
from orbitwatch.ingestion.models import (
    SatcatPayload,
    GPPayload,
    KIndexPayload,
    SolarIndicesPayload,
    IngestResponse,
)

settings = get_settings()

app = FastAPI(title="ORBITWATCH Ingestion API")

client: Optional[MongoClient] = None
db = None

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)):
    if not api_key or api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key"
        )
    return api_key

SOURCE_MODELS = {
    "satcat": SatcatPayload,
    "gp": GPPayload,
    "k_index": KIndexPayload,
    "solar_indices": SolarIndicesPayload,
}

def get_natural_key(source: str, record: dict) -> str:
    """Extract natural key based on the source collection rules."""
    if source == "satcat":
        return str(record.get("NORAD_CAT_ID", ""))
    elif source == "gp":
        return f"{record.get('NORAD_CAT_ID', '')}_{record.get('EPOCH', '')}"
    elif source == "k_index":
        return str(record.get("time_tag", ""))
    elif source == "solar_indices":
        return str(record.get("time-tag", record.get("time_tag", "")))
    return ""

def generate_payload_hash(payload: dict) -> str:
    """Generate SHA-256 hash of canonical JSON payload."""
    canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

@app.on_event("startup")
def startup_db_client():
    global client, db
    client = MongoClient(settings.mongo_uri)
    db = client[settings.mongo_db]
    
    # Initialize collections and indexes safely
    collections = ["raw_satcat", "raw_gp", "raw_k_index", "raw_solar_indices"]
    for coll_name in collections:
        coll = db[coll_name]
        # Idempotency index
        coll.create_index(
            [("source", ASCENDING), ("natural_key", ASCENDING), ("payload_hash", ASCENDING)],
            unique=True,
            background=True
        )
        coll.create_index("batch_id", background=True)
        coll.create_index("ingested_at", background=True)

@app.on_event("shutdown")
def shutdown_db_client():
    if client:
        client.close()

@app.get("/health")
def health_check():
    try:
        if db is not None:
            # ping db
            db.command("ping")
            return {"status": "ok", "db": "connected"}
    except Exception:
        return {"status": "error", "db": "disconnected"}
    return {"status": "error", "db": "uninitialized"}

@app.post("/ingest/{source}", response_model=IngestResponse)
async def ingest_data(
    source: str,
    body: Union[Dict[str, Any], List[Dict[str, Any]]] = Body(
        ...,
        openapi_examples={
            "satcat_example": {
                "summary": "Sample Satellite Payload",
                "value": {
                    "NORAD_CAT_ID": 99999,
                    "OBJECT_NAME": "PROJECT-ORBITWATCH",
                    "OBJECT_TYPE": "PAY",
                    "OWNER": "IND",
                    "LAUNCH_DATE": "2026-10-15"
                }
            }
        }
    ),
    api_key: str = Depends(verify_api_key)
):
    if source not in SOURCE_MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source}")
        
    if isinstance(body, dict):
        records = [body]
    elif isinstance(body, list):
        records = body
    else:
        raise HTTPException(status_code=422, detail="Body must be an object or list of objects")
        
    if len(records) > 5000:
        raise HTTPException(status_code=413, detail="Payload too large. Max 5,000 records per request.")
        
    batch_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)
    
    ModelClass = SOURCE_MODELS[source]
    
    valid_documents = []
    rejected_documents = []
    
    for record in records:
        try:
            # Validate with Pydantic
            validated = ModelClass(**record)
            # We store the *original* record as payload to be perfectly faithful
            natural_key = get_natural_key(source, record)
            payload_hash = generate_payload_hash(record)
            
            doc = {
                "payload": record,
                "source": source,
                "batch_id": batch_id,
                "ingested_at": datetime.now(timezone.utc),
                "natural_key": natural_key,
                "payload_hash": payload_hash,
                "schema_version": 1,
            }
            valid_documents.append(InsertOne(doc))
        except ValidationError as e:
            rejected_documents.append({
                "source": source,
                "batch_id": batch_id,
                "reason": str(e),
                "received_at": datetime.now(timezone.utc),
                "raw_body": record
            })
            
    inserted_count = 0
    duplicate_count = 0
    rejected_count = len(rejected_documents)
    
    if rejected_documents:
        # store rejected
        db.rejected_events.insert_many(rejected_documents, ordered=False)
        
    if valid_documents:
        coll = db[f"raw_{source}"]
        try:
            result = coll.bulk_write(valid_documents, ordered=False)
            inserted_count = result.inserted_count
        except BulkWriteError as bwe:
            # Count duplicates (code 11000 is duplicate key)
            inserted_count = bwe.details['nInserted']
            for err in bwe.details.get('writeErrors', []):
                if err['code'] == 11000:
                    duplicate_count += 1
                else:
                    # other errors we should probably log, but keep going
                    pass
                    
    finished_at = datetime.now(timezone.utc)
    
    # Store ingest batch metadata
    db.ingest_batches.insert_one({
        "batch_id": batch_id,
        "source": source,
        "received_count": len(records),
        "inserted_count": inserted_count,
        "duplicate_count": duplicate_count,
        "rejected_count": rejected_count,
        "started_at": started_at,
        "finished_at": finished_at
    })
    
    return IngestResponse(
        batch_id=batch_id,
        received=len(records),
        inserted=inserted_count,
        duplicates=duplicate_count,
        rejected=rejected_count
    )

@app.get("/records/{source}")
def get_records(source: str, limit: int = 100, skip: int = 0, batch_id: Optional[str] = None, norad_cat_id: Optional[str] = None):
    if source not in SOURCE_MODELS:
        raise HTTPException(status_code=404, detail="Unknown source")
    
    limit = min(limit, 200)
    query = {}
    if batch_id:
        query["batch_id"] = batch_id
    if norad_cat_id and source in ["satcat", "gp"]:
        query["payload.NORAD_CAT_ID"] = {"$in": [norad_cat_id, int(norad_cat_id)] if norad_cat_id.isdigit() else [norad_cat_id]}
        
    coll = db[f"raw_{source}"]
    cursor = coll.find(query, {"_id": 0}).skip(skip).limit(limit)
    return list(cursor)

@app.get("/stats")
def get_stats():
    stats = {}
    for coll_name in ["raw_satcat", "raw_gp", "raw_k_index", "raw_solar_indices", "rejected_events"]:
        stats[coll_name] = db[coll_name].count_documents({})
        
    recent_batches = list(db.ingest_batches.find({}, {"_id": 0}).sort("started_at", -1).limit(5))
    stats["recent_batches"] = recent_batches
    return stats
