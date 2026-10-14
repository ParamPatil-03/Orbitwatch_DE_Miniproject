"""
Tests for FastAPI ingestion service.
Covers validation, duplicates, rejections, and authentication.
"""
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

import orbitwatch.ingestion.api as api_mod
from orbitwatch.ingestion.api import app

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def test_db_setup():
    settings = api_mod.settings
    try:
        mongo_client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=2000)
        mongo_client.admin.command('ping')
    except Exception:
        pytest.skip("MongoDB is unreachable, skipping integration tests.")
        
    api_mod.client = mongo_client
    api_mod.db = mongo_client["orbitwatch_test"]
    from pymongo import ASCENDING
    for coll_name in ["raw_satcat", "raw_gp", "raw_k_index", "raw_solar_indices"]:
        api_mod.db[coll_name].create_index(
            [("source", ASCENDING), ("natural_key", ASCENDING), ("payload_hash", ASCENDING)],
            unique=True,
        )
    yield
    mongo_client.drop_database("orbitwatch_test")
    mongo_client.close()
    api_mod.client = None
    api_mod.db = None

def _headers():
    return {"X-API-Key": api_mod.settings.api_key}

def test_api_requires_auth():
    resp = client.post("/ingest/satcat", json={"NORAD_CAT_ID": "12345"})
    assert resp.status_code == 401

def test_unknown_source():
    resp = client.post("/ingest/unknown", json={"NORAD_CAT_ID": "12345"}, headers=_headers())
    assert resp.status_code == 404

def test_valid_record_insertion():
    payload = {"NORAD_CAT_ID": "12345", "OBJECT_NAME": "TEST SAT"}
    resp = client.post("/ingest/satcat", json=payload, headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["received"] == 1
    assert data["inserted"] == 1
    assert data["duplicates"] == 0
    assert data["rejected"] == 0
    
def test_duplicate_record_insertion():
    payload = {"NORAD_CAT_ID": "99999", "OBJECT_NAME": "DUP SAT"}
    
    resp1 = client.post("/ingest/satcat", json=payload, headers=_headers())
    assert resp1.status_code == 200
    assert resp1.json()["inserted"] == 1
    
    resp2 = client.post("/ingest/satcat", json=payload, headers=_headers())
    assert resp2.status_code == 200
    assert resp2.json()["inserted"] == 0
    assert resp2.json()["duplicates"] == 1

def test_missing_natural_key_rejected():
    payload = {"OBJECT_NAME": "NO ID SAT"} 
    resp = client.post("/ingest/satcat", json=payload, headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["received"] == 1
    assert data["inserted"] == 0
    assert data["duplicates"] == 0
    assert data["rejected"] == 1
