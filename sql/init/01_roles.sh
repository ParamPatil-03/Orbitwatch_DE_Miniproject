#!/usr/bin/env bash
# ORBITWATCH – sql/init/01_roles.sh
#
# PURPOSE: Create the application-level PostgreSQL roles on first database start.
#
# WHY A SHELL SCRIPT?
#   PostgreSQL's plain .sql init files cannot read shell environment variables
#   (e.g. $ETL_DB_PASSWORD).  Only shell scripts (.sh) in the initdb directory
#   can access the container's environment, so we use psql here to run the
#   CREATE ROLE statements with the passwords injected at runtime.
#
# SAFETY: The script checks whether each role already exists before trying to
#   create it, making it safe to re-run (though Postgres only runs initdb scripts
#   once, on an empty data directory).
#
# This script runs as the postgres superuser inside the container.

set -euo pipefail

echo "==> 01_roles.sh: Creating application roles…"

# ── ETL user (read-write pipeline role) ───────────────────────────────────────
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (
            SELECT FROM pg_catalog.pg_roles WHERE rolname = '${ETL_DB_USER}'
        ) THEN
            CREATE ROLE "${ETL_DB_USER}"
                WITH LOGIN
                     NOSUPERUSER
                     NOCREATEROLE
                     NOCREATEDB
                     PASSWORD '${ETL_DB_PASSWORD}';
            RAISE NOTICE 'Role "${ETL_DB_USER}" created.';
        ELSE
            RAISE NOTICE 'Role "${ETL_DB_USER}" already exists, skipping.';
        END IF;
    END
    \$\$;
EOSQL

# ── Dashboard user (read-only role) ───────────────────────────────────────────
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (
            SELECT FROM pg_catalog.pg_roles WHERE rolname = '${DASHBOARD_DB_USER}'
        ) THEN
            CREATE ROLE "${DASHBOARD_DB_USER}"
                WITH LOGIN
                     NOSUPERUSER
                     NOCREATEROLE
                     NOCREATEDB
                     PASSWORD '${DASHBOARD_DB_PASSWORD}';
            RAISE NOTICE 'Role "${DASHBOARD_DB_USER}" created.';
        ELSE
            RAISE NOTICE 'Role "${DASHBOARD_DB_USER}" already exists, skipping.';
        END IF;
    END
    \$\$;
EOSQL

echo "==> 01_roles.sh: Done."
