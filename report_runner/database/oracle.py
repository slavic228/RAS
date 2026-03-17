"""
Oracle database connector using the oracledb driver (python-oracledb).

Credentials are read from environment variables following the naming convention:
  DB_{ALIAS_UPPER}_DSN
  DB_{ALIAS_UPPER}_USER
  DB_{ALIAS_UPPER}_PASSWORD

Example alias "oracle_prod" → env keys:
  DB_ORACLE_PROD_DSN, DB_ORACLE_PROD_USER, DB_ORACLE_PROD_PASSWORD
"""

from __future__ import annotations

import os
from typing import Any

import oracledb

from report_runner.config.models import ConfigurationError
from report_runner.database.base import DatabaseConnector, DatabaseError


class OracleConnector(DatabaseConnector):
    """Wraps a single oracledb connection for one query lifecycle."""

    def __init__(self, alias: str) -> None:
        prefix = f"DB_{alias.upper().replace('-', '_')}"
        dsn = self._require_env(f"{prefix}_DSN", alias)
        user = self._require_env(f"{prefix}_USER", alias)
        password = self._require_env(f"{prefix}_PASSWORD", alias)

        try:
            self._connection = oracledb.connect(user=user, password=password, dsn=dsn)
        except oracledb.Error as exc:
            raise DatabaseError(
                f"Failed to connect to Oracle database alias '{alias}': {exc}"
            ) from exc

    # ── DatabaseConnector interface ───────────────────────────────────────────

    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(sql)
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except oracledb.Error as exc:
            raise DatabaseError(f"Oracle query execution failed: {exc}") from exc

    def close(self) -> None:
        try:
            self._connection.close()
        except oracledb.Error:
            pass  # Best-effort close — don't mask the original error.

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
