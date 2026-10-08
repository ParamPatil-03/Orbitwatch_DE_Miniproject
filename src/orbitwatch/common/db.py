# ORBITWATCH – src/orbitwatch/common/db.py
# Low-level database connection helpers.
# This file contains ONLY connection factory functions – no business logic.
# Import get_postgres_engine() or get_mongo_client() wherever you need a connection.

from __future__ import annotations

from typing import Literal

import pymongo
import pymongo.mongo_client
from sqlalchemy import Engine, create_engine


def get_postgres_engine(role: Literal["etl", "dashboard"]) -> Engine:
    """
    Create and return a SQLAlchemy 2.x :class:`~sqlalchemy.engine.Engine`
    connected to PostgreSQL using the psycopg v3 driver.

    Args:
        role: Which database role to connect as.
              ``"etl"``       – the read-write ETL pipeline user.
              ``"dashboard"`` – the read-only dashboard user.

    Returns:
        A :class:`~sqlalchemy.engine.Engine` instance.  Connections are not
        opened until you actually use the engine (lazy connection pool).

    Raises:
        ValueError: If *role* is not ``"etl"`` or ``"dashboard"``.
        RuntimeError: If the settings cannot be loaded (missing .env values).
    """
    from config.settings import get_settings  # local import to avoid circular deps

    settings = get_settings()

    if role == "etl":
        url = settings.etl_postgres_url
    elif role == "dashboard":
        url = settings.dashboard_postgres_url
    else:
        raise ValueError(
            f"Unknown role '{role}'. Must be 'etl' or 'dashboard'."
        )

    engine = create_engine(
        url,
        # Keep the connection pool small for a single-laptop setup.
        pool_size=3,
        max_overflow=2,
        # Fail quickly so errors surface during development, not silently hang.
        connect_args={
            "connect_timeout": 5,  # seconds – psycopg v3 keyword
        },
        # Echo SQL statements when LOG_LEVEL is DEBUG (helpful for learning).
        echo=(settings.log_level.upper() == "DEBUG"),
    )
    return engine


def get_mongo_client() -> pymongo.mongo_client.MongoClient:  # type: ignore[type-arg]
    """
    Create and return a :class:`~pymongo.mongo_client.MongoClient` connected
    to MongoDB using the URI from settings.

    The client uses short timeouts so failures are immediately obvious during
    development, rather than waiting 30 seconds for the default socket timeout.

    Returns:
        A :class:`~pymongo.mongo_client.MongoClient` instance.
        PyMongo pools connections internally; you can share this client across
        threads and should avoid creating one per request.

    Raises:
        RuntimeError: If the settings cannot be loaded (missing .env values).
    """
    from config.settings import get_settings  # local import to avoid circular deps

    settings = get_settings()

    client: pymongo.mongo_client.MongoClient = pymongo.MongoClient(  # type: ignore[type-arg]
        settings.mongo_uri,
        # Fail after 3 seconds if the server is unreachable.
        serverSelectionTimeoutMS=3_000,
        connectTimeoutMS=3_000,
        socketTimeoutMS=5_000,
    )
    return client
