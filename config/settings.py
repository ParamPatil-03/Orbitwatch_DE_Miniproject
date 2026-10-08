# ORBITWATCH – config/settings.py
# Central configuration loader using pydantic-settings.
# All values are read from the .env file at startup.
# Import get_settings() anywhere in the project to access configuration.

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All application settings, loaded from environment variables / .env file.

    pydantic-settings reads variables in this order (highest wins):
      1. Real environment variables (e.g. set in the shell or Docker)
      2. Values in the .env file at the project root
      3. Default values defined here (if any)

    If a required variable is missing the app will raise a clear ValidationError
    listing every missing field before starting.
    """

    model_config = SettingsConfigDict(
        # Look for .env relative to the project root (one level above config/).
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        # Allow extra environment variables without raising errors.
        extra="ignore",
    )

    # ── PostgreSQL – admin account ─────────────────────────────────────────────
    postgres_host: str = Field(..., description="Hostname for PostgreSQL")
    postgres_port: int = Field(5432, description="Port for PostgreSQL")
    postgres_db: str = Field(..., description="Database name")
    postgres_user: str = Field(..., description="Admin user for PostgreSQL")
    postgres_password: str = Field(..., description="Admin password for PostgreSQL")

    # ── PostgreSQL – ETL role (read-write) ────────────────────────────────────
    etl_db_user: str = Field(..., description="ETL pipeline user (read-write)")
    etl_db_password: str = Field(..., description="ETL pipeline user password")

    # ── PostgreSQL – Dashboard role (read-only) ────────────────────────────────
    dashboard_db_user: str = Field(..., description="Dashboard user (read-only)")
    dashboard_db_password: str = Field(..., description="Dashboard user password")

    # ── MongoDB ────────────────────────────────────────────────────────────────
    mongo_host: str = Field(..., description="Hostname for MongoDB")
    mongo_port: int = Field(27017, description="Port for MongoDB")
    mongo_user: str = Field(..., description="MongoDB root user")
    mongo_password: str = Field(..., description="MongoDB root password")
    mongo_db: str = Field(..., description="MongoDB default database name")

    # ── Redpanda / Kafka ──────────────────────────────────────────────────────
    kafka_bootstrap_servers: str = Field(
        ..., description="Kafka bootstrap servers (e.g. localhost:19092)"
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = Field("INFO", description="Logging level (DEBUG, INFO, WARNING…)")
    log_dir: str = Field("logs", description="Directory where log files are written")

    # ── API ───────────────────────────────────────────────────────────────────
    api_key: str = Field(..., description="API key for ingestion endpoints")

    # ── Computed properties ────────────────────────────────────────────────────

    @computed_field  # type: ignore[misc]
    @property
    def etl_postgres_url(self) -> str:
        """SQLAlchemy connection URL for the ETL user (psycopg v3 driver)."""
        return (
            f"postgresql+psycopg://{self.etl_db_user}:{self.etl_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def dashboard_postgres_url(self) -> str:
        """SQLAlchemy connection URL for the dashboard user (psycopg v3 driver)."""
        return (
            f"postgresql+psycopg://{self.dashboard_db_user}:{self.dashboard_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[misc]
    @property
    def mongo_uri(self) -> str:
        """PyMongo connection URI including credentials."""
        return (
            f"mongodb://{self.mongo_user}:{self.mongo_password}"
            f"@{self.mongo_host}:{self.mongo_port}/{self.mongo_db}"
            "?authSource=admin"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the application settings, loaded once and cached for the process lifetime.

    Raises:
        pydantic_core.ValidationError: If any required environment variable is
            missing or has an invalid type.  The error message lists every
            missing field by name so you know exactly what to add to .env.
    """
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:
        # Re-raise with a human-readable prefix so students can act on it.
        raise RuntimeError(
            "\n\n[ORBITWATCH] Failed to load settings.\n"
            "Make sure you have copied .env.example to .env and filled in all values.\n"
            f"Details: {exc}"
        ) from exc
