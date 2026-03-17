"""
QueryPollerPreconditionChecker

Polls a database query at regular intervals until:
  - The query returns a non-null, non-empty value → precondition passes.
  - The current local time reaches or exceeds `deadline_time` → exit(1).

Protocol (from the spec):
  1. Execute query.
  2. If result is not null and not empty → pass.
  3. Check deadline BEFORE sleeping.
  4. If deadline reached → log error, exit(1).
  5. Sleep poll_interval_minutes, then repeat.

The query must return exactly one row and one column.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

from loguru import logger

from report_runner.config.models import PreconditionConfig
from report_runner.database.base import DatabaseError
from report_runner.database.factory import DatabaseConnectorFactory
from report_runner.preconditions.base import PreconditionChecker


class QueryPollerPreconditionChecker(PreconditionChecker):
    """Polls a DB query until the result is non-null/non-empty or deadline passes."""

    def __init__(self, db_factory: DatabaseConnectorFactory) -> None:
        self._db_factory = db_factory

    def check(self, config: PreconditionConfig) -> bool:
        deadline_hour, deadline_minute = map(int, config.deadline_time.split(":"))

        logger.info(
            "Precondition '{}': starting poll (deadline {}, interval {}m).",
            config.description,
            config.deadline_time,
            config.poll_interval_minutes,
        )

        while True:
            result_value = self._poll_once(config)

            logger.info(
                "Precondition '{}': query result = {!r} at {}",
                config.description,
                result_value,
                datetime.now().strftime("%H:%M:%S"),
            )

            if result_value is not None and str(result_value).strip() != "":
                logger.info(
                    "Precondition '{}' passed (value={!r}).",
                    config.description,
                    result_value,
                )
                return True

            # Deadline check happens BEFORE sleep.
            now = datetime.now()
            deadline_today = now.replace(
                hour=deadline_hour,
                minute=deadline_minute,
                second=0,
                microsecond=0,
            )
            if now >= deadline_today:
                logger.error(
                    "Precondition '{}' not met by deadline {}. Aborting workflow.",
                    config.description,
                    config.deadline_time,
                )
                sys.exit(1)

            wait_seconds = config.poll_interval_minutes * 60
            logger.info(
                "Precondition '{}': not met (value={!r}). Retrying in {} min...",
                config.description,
                result_value,
                config.poll_interval_minutes,
            )
            time.sleep(wait_seconds)

    def _poll_once(self, config: PreconditionConfig) -> object:
        """Execute the precondition SQL and return the single scalar value."""
        from pathlib import Path

        sql_path = Path(config.sql_file)
        if not sql_path.exists():
            logger.error(
                "Precondition '{}': SQL file not found: {}",
                config.description,
                sql_path,
            )
            sys.exit(1)

        sql = sql_path.read_text(encoding="utf-8").strip()
        connector = self._db_factory.create(config.database_alias)
        try:
            rows = connector.execute_query(sql)
        except DatabaseError as exc:
            logger.exception(
                "Precondition '{}': database error during poll: {}",
                config.description,
                exc,
            )
            # Treat a DB error as "not ready" — it will retry or hit deadline.
            return None
        finally:
            connector.close()

        if not rows:
            return None

        first_row = rows[0]
        if not first_row:
            return None

        # Return the value of the first (and expected only) column.
        return next(iter(first_row.values()))
