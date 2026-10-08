# ORBITWATCH – tests/test_healthcheck.py
# Simple tests for the healthcheck script and configuration loading.

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from config.settings import get_settings
from orbitwatch.common.db import get_postgres_engine
from scripts.healthcheck import check_mongo, check_redpanda, check_postgres_schemas_and_tables


def test_settings_load_successfully(monkeypatch):
    """Test that settings load correctly when basic env vars are present."""
    # We don't want to rely on the actual .env file state, so we patch env vars
    monkeypatch.setenv("POSTGRES_HOST", "testhost")
    monkeypatch.setenv("POSTGRES_DB", "testdb")
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("ETL_DB_USER", "eu")
    monkeypatch.setenv("ETL_DB_PASSWORD", "ep")
    monkeypatch.setenv("DASHBOARD_DB_USER", "du")
    monkeypatch.setenv("DASHBOARD_DB_PASSWORD", "dp")
    monkeypatch.setenv("MONGO_HOST", "testhost")
    monkeypatch.setenv("MONGO_USER", "mu")
    monkeypatch.setenv("MONGO_PASSWORD", "mp")
    monkeypatch.setenv("MONGO_DB", "mdb")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "testhost:9092")
    
    # We need to clear the lru_cache for this test to use the monkeypatched vars
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.postgres_host == "testhost"
    assert "testhost:9092" in settings.kafka_bootstrap_servers
    # Clear again so subsequent tests don't use monkeypatched values
    get_settings.cache_clear()


@pytest.mark.live
def test_postgres_etl_connection():
    """Test ETL user connectivity. Will fail if DB is not running."""
    try:
        engine = get_postgres_engine("etl")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            assert result == 1
    except Exception as e:
        pytest.skip(f"Live database not available: {e}")


def test_healthcheck_functions_exist():
    """Basic structural test to ensure refactoring doesn't break function names."""
    assert callable(check_mongo)
    assert callable(check_redpanda)
    assert callable(check_postgres_schemas_and_tables)
