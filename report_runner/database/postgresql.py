"""
PostgreSQL connector using psycopg2.

Credential convention (all env variables):
  DB_{ALIAS_UPPER}_HOST
  DB_{ALIAS_UPPER}_PORT      (default: 5432)
  DB_{ALIAS_UPPER}_NAME
  DB_{ALIAS_UPPER}_USER
  DB_{ALIAS_UPPER}_PASSWORD

Example alias "postgres_analytics" → env keys:
  DB_POSTGRES_ANALYTICS_HOST, DB_POSTGRES_ANALYTICS_PORT, etc.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg2
import psycopg2.extras

from report_runner.config.models import ConfigurationError
from report_runner.database.base import DatabaseConnector, DatabaseError


class PostgresConnector(DatabaseConnector):
    """Wraps a single psycopg2 connection for one query lifecycle."""

    def __init__(self, alias: str) -> None:
        prefix = f"DB_{alias.upper().replace('-', '_')}"
        host = self._require_env(f"{prefix}_HOST", alias)
        port = int(os.environ.get(f"{prefix}_PORT", "5432"))
        dbname = self._require_env(f"{prefix}_NAME", alias)
        user = self._require_env(f"{prefix}_USER", alias)
        password = self._require_env(f"{prefix}_PASSWORD", alias)

        try:
            self._connection = psycopg2.connect(
                host=host,
                port=port,
                dbname=dbname,
                user=user,
                password=password,
            )
        except psycopg2.Error as exc:
            raise DatabaseError(
                f"Failed to connect to PostgreSQL database alias '{alias}': {exc}"
            ) from exc

    # ── DatabaseConnector interface ───────────────────────────────────────────

    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        try:
            with self._connection.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cursor:
                cursor.execute(sql)
                return [dict(row) for row in cursor.fetchall()]
        except psycopg2.Error as exc:
            raise DatabaseError(f"PostgreSQL query execution failed: {exc}") from exc

    def close(self) -> None:
        try:
            self._connection.close()
        except psycopg2.Error:
            pass

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _require_env(key: str, alias: str) -> str:
        value = os.environ.get(key)
        if not value:
            raise ConfigurationError(
                f"Missing environment variable '{key}' required for "
                f"database alias '{alias}'."
            )
        return value
