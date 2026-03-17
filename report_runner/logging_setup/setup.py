"""
Loguru logging configuration.

Sets up two sinks:
  1. Rotating file sink: {LOG_DIR}/{workflow_name}_{date}.log
  2. Stdout sink at INFO level (mirrors to console)

All settings come from environment variables (loaded by dotenv before this runs):
  LOG_DIR       — directory for log files (default: "logs")
  LOG_LEVEL     — minimum log level (default: "INFO")
  LOG_ROTATION  — file rotation trigger (default: "10 MB")
  LOG_RETENTION — log file retention period (default: "30 days")

The log format is intentionally consistent between file and stdout so that
log output can be compared or grepped uniformly.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

from loguru import logger

_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}"


def configure_logging(workflow_name: str, log_level_override: str | None = None) -> None:
    """
    Configure all loguru sinks.

    Must be called once at application startup, before any other module
    starts emitting log messages.

    Args:
        workflow_name:      Used to build the log filename.
        log_level_override: If provided, overrides LOG_LEVEL from .env.
    """
    # Remove loguru's default sink (stderr) — we manage all sinks explicitly.
    logger.remove()

    log_level = log_level_override or os.environ.get("LOG_LEVEL", "INFO")
    log_dir = Path(os.environ.get("LOG_DIR", "logs"))
    log_rotation = os.environ.get("LOG_ROTATION", "10 MB")
    log_retention = os.environ.get("LOG_RETENTION", "30 days")

    log_dir.mkdir(parents=True, exist_ok=True)

    run_date = date.today().strftime("%Y-%m-%d")
    safe_name = workflow_name.replace(" ", "_").replace("/", "_")
    log_filename = log_dir / f"{safe_name}_{run_date}.log"

    # ── File sink (rotating) ──────────────────────────────────────────────────
    logger.add(
        str(log_filename),
        level=log_level,
        format=_LOG_FORMAT,
        rotation=log_rotation,
        retention=log_retention,
        encoding="utf-8",
        backtrace=True,
        diagnose=False,   # Disable variable values in tracebacks for security.
    )

    # ── Stdout sink ───────────────────────────────────────────────────────────
    logger.add(
        sys.stdout,
        level="INFO",   # Always show INFO+ on console regardless of file level.
        format=_LOG_FORMAT,
        colorize=True,
    )

    logger.info("Logging configured: level={}, file={}", log_level, log_filename)
