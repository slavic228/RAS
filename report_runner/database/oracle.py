"""
Oracle database connector using the oracledb driver (python-oracledb).

Credentials are read from environment variables following the naming convention:
  DB_{ALIAS_UPPER}_DSN      — host:port/service_name  (EZConnect format)
  DB_{ALIAS_UPPER}_USER     — username (may contain @ for domain users)
  DB_{ALIAS_UPPER}_PASSWORD — password (may contain special characters)

Example alias "oracle_prod" → env keys:
  DB_ORACLE_PROD_DSN, DB_ORACLE_PROD_USER, DB_ORACLE_PROD_PASSWORD

Connection approach: builds a single EZConnect string
  [user]/[password]@host:port/service_name

When user or password contain special characters (@, /, space, brackets),
they are wrapped in Oracle double-quote syntax INSIDE the connection string.
This is the correct quoting context — double-quoting works in the DSN string,
not as Python keyword arguments to oracledb.connect().
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

        # Build a single EZConnect string: [user]/[password]@dsn
        # Quoting special chars (@ / space [ ]) in this context is correct —
        # the double-quote syntax applies to the DSN string parser, not to
        # keyword arguments.  This matches the pattern:
        #   oracledb.connect("user/password@host:port/service")
        connect_string = _build_connect_string(user, password, dsn)

        try:
            self._connection = oracledb.connect(connect_string)
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


# ── Module-level helpers ──────────────────────────────────────────────────────

def _build_connect_string(user: str, password: str, dsn: str) -> str:
    """
    Assemble the EZConnect string: [user]/[password]@dsn

    Special characters in user or password are handled by wrapping the value
    in Oracle double-quote syntax.  Any embedded double-quote characters are
    escaped by doubling them ("").
    """
    return f"{_oracle_quote(user)}/{_oracle_quote(password)}@{dsn}"


def _oracle_quote(value: str) -> str:
    """
    Wrap a credential in Oracle double-quote syntax when it contains characters
    that the EZConnect string parser would otherwise misinterpret:

      @  — split point between credentials and host
      /  — split point between user and password
      space, (, ) — structural characters in full TNS descriptors

    Embedded double-quote characters within the value are escaped by doubling.
    Plain values (no special chars) are returned unchanged.
    """
    _SPECIAL = {"@", "/", " ", "(", ")"}
    if any(ch in value for ch in _SPECIAL):
        escaped = value.replace('"', '""')
        return f'"{escaped}"'
    return value
