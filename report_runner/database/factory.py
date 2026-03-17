"""
DatabaseConnectorFactory

Resolves which DatabaseConnector implementation to use based on a naming
convention in the database alias:
  - alias starts with "oracle"     → OracleConnector
  - alias starts with "mssql"      → MssqlConnector
  - alias starts with "postgres"   → PostgresConnector

The alias comes directly from the YAML `database_alias` field, giving the
workflow author full control over which engine is used for each alias.

Adding a new database type requires:
  1. A new concrete class in database/<engine>.py
  2. One new elif branch here
  3. No changes anywhere else in the codebase
"""

from __future__ import annotations

from report_runner.config.models import ConfigurationError
from report_runner.database.base import DatabaseConnector


class DatabaseConnectorFactory:
    """Creates a DatabaseConnector for the given alias string."""

    def create(self, alias: str) -> DatabaseConnector:
        """
        Instantiate and return the correct DatabaseConnector.

        The connection is opened inside the connector's __init__, so the
        caller must call .close() when done to release resources.
        """
        alias_lower = alias.lower()

        if alias_lower.startswith("oracle"):
            from report_runner.database.oracle import OracleConnector
            return OracleConnector(alias)

        if alias_lower.startswith("mssql"):
            from report_runner.database.mssql import MssqlConnector
            return MssqlConnector(alias)

        if alias_lower.startswith("postgres"):
            from report_runner.database.postgresql import PostgresConnector
            return PostgresConnector(alias)

        raise ConfigurationError(
            f"Cannot determine database engine for alias '{alias}'. "
            f"Alias must start with 'oracle', 'mssql', or 'postgres'."
        )
