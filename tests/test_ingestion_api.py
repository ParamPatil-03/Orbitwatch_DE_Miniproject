"""
Tests for FastAPI ingestion service.
Covers validation, duplicates, rejections, and authentication.
"""
import os
import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

os.environ["API_KEY"] = "test_key"
os.environ["MONGO_DB"] = "orbitwatch_test"

from orbitwatch.ingestion.api import app, startup_db_client, shutdown_db_client
from config.settings import get_settings

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def test_db_setup():
    settings = get_settings()
    try:
        mongo_client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=2000)
        mongo_client.admin.command('ping')
    except Exception:
        pytest.skip("MongoDB is unreachable, skipping integration tests.")
        
    startup_db_client()
    yield
    shutdown_db_client()
    mongo_client.drop_database("orbitwatch_test")
    mongo_client.close()

def test_api_requires_auth():
    resp = client.post("/ingest/satcat", json={"NORAD_CAT_ID": "12345"})
    assert resp.status_code == 401

def test_unknown_source():
    headers = {"X-API-Key": "test_key"}
    resp = client.post("/ingest/unknown", json={"NORAD_CAT_ID": "12345"}, headers=headers)
    assert resp.status_code == 404

def test_valid_record_insertion():
    headers = {"X-API-Key": "test_key"}
    payload = {"NORAD_CAT_ID": "12345", "OBJECT_NAME": "TEST SAT"}
    resp = client.post("/ingest/satcat", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["received"] == 1
    assert data["inserted"] == 1
    assert data["duplicates"] == 0
    assert data["rejected"] == 0
    
def test_duplicate_record_insertion():
    headers = {"X-API-Key": "test_key"}
    payload = {"NORAD_CAT_ID": "99999", "OBJECT_NAME": "DUP SAT"}
    
    resp1 = client.post("/ingest/satcat", json=payload, headers=headers)
    assert resp1.status_code == 200
    assert resp1.json()["inserted"] == 1
    
    resp2 = client.post("/ingest/satcat", json=payload, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["inserted"] == 0
    assert resp2.json()["duplicates"] == 1

def test_missing_natural_key_rejected():
    headers = {"X-API-Key": "test_key"}
    payload = {"OBJECT_NAME": "NO ID SAT"} 
    resp = client.post("/ingest/satcat", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["received"] == 1
    assert data["inserted"] == 0
    assert data["rejected"] == 1
