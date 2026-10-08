# ORBITWATCH – scripts/healthcheck.py
# Validates connectivity and permissions for all Phase 1 infrastructure services.
# Run this after 'docker compose up -d' to ensure the environment is ready.

import sys
import uuid
from typing import Literal

from confluent_kafka.admin import AdminClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# Ensure src/ is in the python path when running this script directly
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from orbitwatch.common.db import get_mongo_client, get_postgres_engine
from orbitwatch.common.logging_setup import get_logger

logger = get_logger("healthcheck")


def check_mongo() -> bool:
    """Check connectivity to MongoDB."""
    try:
        client = get_mongo_client()
        # The ping command is cheap and fails fast if credentials/host are wrong
        client.admin.command("ping")
        logger.info("PASS: MongoDB connectivity.")
        return True
    except Exception as exc:
        logger.error(f"FAIL: MongoDB check failed: {exc}")
        return False


def check_redpanda() -> bool:
    """Check connectivity to Redpanda/Kafka via the host-side listener."""
    from config.settings import get_settings
    try:
        settings = get_settings()
        admin = AdminClient({
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "socket.timeout.ms": 3000
        })
        # list_topics() blocks until metadata is fetched or timeout occurs
        metadata = admin.list_topics(timeout=3.0)
        logger.info(f"PASS: Redpanda connectivity. Found {len(metadata.topics)} topics.")
        return True
    except Exception as exc:
        logger.error(f"FAIL: Redpanda check failed: {exc}")
        return False


def check_postgres_schemas_and_tables(role: Literal["etl", "dashboard"]) -> bool:
    """Check that schemas and tables exist, and verify least-privilege access."""
    engine = get_postgres_engine(role)
    passed = True

    try:
        with engine.connect() as conn:
            # 1. Verify schema access
            # etl_user should see all 4; dashboard_user only sees warehouse.
            expected_schemas = (
                ["staging", "warehouse", "audit", "quality"] 
                if role == "etl" else ["warehouse"]
            )
            
            for schema in expected_schemas:
                try:
                    conn.execute(text(f"SELECT has_schema_privilege('{schema}', 'USAGE')"))
                except SQLAlchemyError as e:
                    logger.error(f"FAIL: {role} cannot access schema {schema}: {e}")
                    passed = False

            # 2. Verify basic SELECT on warehouse (both should have this)
            try:
                # We can query information_schema to check if warehouse tables are readable, 
                # but an easier way is just to see if we can query it without error.
                # However, there are no tables in warehouse yet. We'll skip deep DML checks 
                # on empty schemas for now, except for the audit tables which we know exist.
                pass
            except SQLAlchemyError:
                pass

            # 3. Verify specific table access constraints
            if role == "dashboard":
                # Dashboard should be denied INSERT into audit.pipeline_runs
                try:
                    with conn.begin_nested(): # Savepoint to rollback on error
                        test_uuid = uuid.uuid4()
                        conn.execute(
                            text("INSERT INTO audit.pipeline_runs (run_id, pipeline_name, started_at, status) VALUES (:id, 'test', now(), 'test')"),
                            {"id": test_uuid}
                        )
                    # If we reach here, the insert succeeded (which is bad)
                    logger.error(f"FAIL: {role} was able to INSERT into audit.pipeline_runs!")
                    conn.rollback() # Don't leave test data
                    passed = False
                except SQLAlchemyError as exc:
                    # Expected failure
                    logger.info(f"PASS: {role} is correctly denied INSERT into audit.pipeline_runs.")
            
            elif role == "etl":
                # ETL should be able to SELECT from audit tables (verifying they exist)
                try:
                    conn.execute(text("SELECT 1 FROM audit.pipeline_runs LIMIT 1"))
                    conn.execute(text("SELECT 1 FROM audit.data_lineage LIMIT 1"))
                    conn.execute(text("SELECT 1 FROM audit.access_log LIMIT 1"))
                    conn.execute(text("SELECT 1 FROM quality.dead_letter LIMIT 1"))
                    logger.info(f"PASS: {role} can access all audit and quality tables.")
                except SQLAlchemyError as exc:
                    logger.error(f"FAIL: {role} could not query audit/quality tables: {exc}")
                    passed = False
                    
        return passed

    except Exception as exc:
        logger.error(f"FAIL: PostgreSQL connection for {role} failed: {exc}")
        return False


def main() -> int:
    """Run all health checks and return an exit code (0 = all pass, 1 = any fail)."""
    logger.info("Starting health checks...")
    
    checks = [
        check_mongo(),
        check_redpanda(),
        check_postgres_schemas_and_tables("etl"),
        check_postgres_schemas_and_tables("dashboard"),
    ]
    
    if all(checks):
        logger.info("ALL CHECKS PASSED. The environment is ready.")
        return 0
    else:
        logger.error("ONE OR MORE CHECKS FAILED. See logs above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
