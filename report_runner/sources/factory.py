"""
DataSourceFactory

Creates the correct DataSource subclass based on the `type` field of a
SourceConfig.  This is the single place in the codebase that knows about
the concrete DataSource implementations.

Adding a new source type requires:
  1. A new class in sources/<type>_source.py
  2. A new branch in this factory
  3. No changes elsewhere
"""

from __future__ import annotations

from report_runner.config.models import ApiSourceConfig, SourceConfig, SqlSourceConfig
from report_runner.database.factory import DatabaseConnectorFactory
from report_runner.sources.api_source import ApiDataSource
from report_runner.sources.base import DataSource
from report_runner.sources.sql_source import SqlDataSource


class DataSourceFactory:
    """Creates DataSource instances from SourceConfig objects."""

    def __init__(self, db_factory: DatabaseConnectorFactory) -> None:
        # Injected so that SqlDataSource can create DB connections on demand.
        self._db_factory = db_factory

    def create(self, config: SourceConfig) -> DataSource:
        if isinstance(config, SqlSourceConfig):
            return SqlDataSource(config, self._db_factory)

        if isinstance(config, ApiSourceConfig):
            return ApiDataSource(config)

        # This branch is unreachable given Pydantic's discriminated union, but
        # it makes the factory exhaustive and is useful if new types are added.
        raise ValueError(
            f"Unknown source config type: {type(config).__name__}"
        )
