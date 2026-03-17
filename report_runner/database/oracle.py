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

        # Oracle's thin driver treats `@` in credentials as a service-name
        # separator (e.g. "user@service").  Wrapping the value in double quotes
        # tells the driver to treat the whole string as a literal credential.
        # Passwords with special chars get the same treatment.
        quoted_user = _oracle_quote(user)
        quoted_password = _oracle_quote(password)

        try:
            self._connection = oracledb.connect(
                user=quoted_user, password=quoted_password, dsn=dsn
            )
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


def _oracle_quote(value: str) -> str:
    """
    Wrap a credential value in double quotes so the oracledb thin driver
    treats it as a literal string rather than parsing special characters.

    Characters that require quoting:
      @  — misinterpreted as a service-name separator
      /  — misinterpreted as a user/password separator
      "  — must be escaped by doubling inside the outer quotes

    Values that are already double-quoted are left unchanged.
    """
    _SPECIAL = {"@", "/", " ", "(", ")"}
    if any(ch in value for ch in _SPECIAL):
        escaped = value.replace('"', '""')  # escape any embedded double-quotes
        return f'"{escaped}"'
    return value
