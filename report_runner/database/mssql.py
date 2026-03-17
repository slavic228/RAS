"""
Microsoft SQL Server connector using pyodbc.

Credential convention:
  DB_{ALIAS_UPPER}_CONNECTION_STRING
  (full ODBC connection string including DRIVER, SERVER, DATABASE, UID, PWD)

Example alias "mssql_dwh" → env key:
  DB_MSSQL_DWH_CONNECTION_STRING
"""

from __future__ import annotations

import os
from typing import Any

import pyodbc

from report_runner.config.models import ConfigurationError
from report_runner.database.base import DatabaseConnector, DatabaseError


class MssqlConnector(DatabaseConnector):
    """Wraps a single pyodbc connection for one query lifecycle."""

    def __init__(self, alias: str) -> None:
        key = f"DB_{alias.upper().replace('-', '_')}_CONNECTION_STRING"
        connection_string = os.environ.get(key)
        if not connection_string:
            raise ConfigurationError(
                f"Missing environment variable '{key}' required for "
                f"database alias '{alias}'."
            )

        try:
            self._connection = pyodbc.connect(connection_string)
        except pyodbc.Error as exc:
            raise DatabaseError(
                f"Failed to connect to MSSQL database alias '{alias}': {exc}"
            ) from exc

    # ── DatabaseConnector interface ───────────────────────────────────────────

    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(sql)
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except pyodbc.Error as exc:
            raise DatabaseError(f"MSSQL query execution failed: {exc}") from exc

    def close(self) -> None:
        try:
            self._connection.close()
        except pyodbc.Error:
            pass
