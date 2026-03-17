"""
SQL data source.

Reads a .sql file from disk, executes it against a DatabaseConnector, and
returns the result rows as a pandas DataFrame.

The connector is created fresh for each fetch() call and closed immediately
after, keeping connection lifetimes short and explicit.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger

from report_runner.config.models import SqlSourceConfig
from report_runner.database.base import DatabaseConnector, DatabaseError
from report_runner.database.factory import DatabaseConnectorFactory
from report_runner.sources.base import DataSource, DataSourceError


class SqlDataSource(DataSource):
    """Executes a .sql file via a DatabaseConnector and returns a DataFrame."""

    def __init__(
        self,
        config: SqlSourceConfig,
        db_factory: DatabaseConnectorFactory,
    ) -> None:
        self._config = config
        self._db_factory = db_factory

    def fetch(self) -> pd.DataFrame:
        sql_path = Path(self._config.sql_file)
        if not sql_path.exists():
            raise DataSourceError(
                f"SQL file not found: '{sql_path}'. "
                f"(source alias '{self._config.alias}')"
            )

        sql = sql_path.read_text(encoding="utf-8").strip()
        if not sql:
            raise DataSourceError(
                f"SQL file '{sql_path}' is empty. "
                f"(source alias '{self._config.alias}')"
            )

        logger.debug(
            "SqlDataSource: fetching '{}' from alias '{}'",
            sql_path.name,
            self._config.database_alias,
        )

        connector: DatabaseConnector = self._db_factory.create(
            self._config.database_alias
        )
        try:
            rows = connector.execute_query(sql)
        except DatabaseError as exc:
            raise DataSourceError(
                f"Database query failed for source '{self._config.alias}': {exc}"
            ) from exc
        finally:
            connector.close()

        df = pd.DataFrame(rows)
        logger.debug(
            "SqlDataSource: '{}' returned {} rows.",
            self._config.alias,
            len(df),
        )
        return df
