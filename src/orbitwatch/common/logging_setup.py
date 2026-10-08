# ORBITWATCH – src/orbitwatch/common/logging_setup.py
# Centralised logging factory used by every module in the project.
# Call get_logger(__name__) at the top of any module to get a configured logger.

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path


def get_logger(
    name: str,
    run_id: str | None = None,
) -> logging.Logger:
    """
    Return a configured :class:`logging.Logger` for the given *name*.

    The logger writes to two destinations:
    - **Console** (stdout) – always active; useful during development.
    - **Rotating file** – writes to ``<LOG_DIR>/<name>.log``; rotates at 5 MB,
      keeps the 3 most recent backups.

    The log level is taken from the ``LOG_LEVEL`` setting (defaults to INFO).

    Duplicate handlers are avoided: calling this function multiple times with
    the same *name* returns the existing logger without adding extra handlers.

    Args:
        name:    Logger name – use ``__name__`` so messages show the module path.
        run_id:  Optional pipeline run identifier appended to every log record.
                 Pass a UUID string when running a pipeline so logs are traceable.

    Returns:
        A fully configured :class:`logging.Logger` instance.
    """
    # Import here to avoid a circular import (settings → logging → settings).
    from config.settings import get_settings  # noqa: PLC0415

    settings = get_settings()

    logger = logging.getLogger(name)

    # ── Guard: do not add handlers a second time ──────────────────────────────
    if logger.handlers:
        return logger

    # ── Log level ─────────────────────────────────────────────────────────────
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # ── Format ────────────────────────────────────────────────────────────────
    # Include run_id in the format string only when one is provided.
    run_id_part = f" [run={run_id}]" if run_id else ""
    fmt = (
        f"%(asctime)s | %(levelname)-8s | %(name)s{run_id_part} | %(message)s"
    )
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S")

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ── Rotating file handler ─────────────────────────────────────────────────
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Use the last segment of the dotted name as the filename (e.g. "db.log").
    safe_name = name.replace(".", "_")
    log_file = log_dir / f"{safe_name}.log"

    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Prevent log records from propagating to the root logger and being printed twice.
    logger.propagate = False

    return logger
