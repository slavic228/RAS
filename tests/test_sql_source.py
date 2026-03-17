"""
Tests for sources/sql_source.py.

Covers:
  - Normal query returns correct DataFrame.
  - SQL file not found raises DataSourceError.
  - Empty SQL file raises DataSourceError.
  - DatabaseError from connector is wrapped in DataSourceError.
  - Connector.close() is always called, even on error.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from report_runner.config.models import SqlSourceConfig
from report_runner.database.base import DatabaseError
from report_runner.sources.base import DataSourceError
from report_runner.sources.sql_source import SqlDataSource


def make_source(tmp_path: Path, sql_content: str = "SELECT 1") -> tuple[SqlDataSource, MagicMock]:
    """Helper: creates a SqlDataSource with a temp SQL file and mock DB factory."""
    sql_file = tmp_path / "query.sql"
    sql_file.write_text(sql_content, encoding="utf-8")

    config = SqlSourceConfig(
        alias="test_source",
        type="sql",
        database_alias="oracle_prod",
        sql_file=str(sql_file),
    )

    mock_connector = MagicMock()
    mock_factory = MagicMock()
    mock_factory.create.return_value = mock_connector

    source = SqlDataSource(config=config, db_factory=mock_factory)
    return source, mock_connector


def test_returns_dataframe_from_rows(tmp_path: Path) -> None:
    """A successful query produces a DataFrame with the correct data."""
    source, mock_connector = make_source(tmp_path)
    mock_connector.execute_query.return_value = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    df = source.fetch()

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert list(df.columns) == ["id", "name"]
    assert df.iloc[0]["name"] == "Alice"


def test_empty_result_returns_empty_dataframe(tmp_path: Path) -> None:
    """A query returning zero rows produces an empty DataFrame."""
    source, mock_connector = make_source(tmp_path)
    mock_connector.execute_query.return_value = []

    df = source.fetch()

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_sql_file_not_found_raises(tmp_path: Path) -> None:
    """Referencing a non-existent SQL file raises DataSourceError."""
    config = SqlSourceConfig(
        alias="missing",
        type="sql",
        database_alias="oracle_prod",
        sql_file=str(tmp_path / "nonexistent.sql"),
    )
    source = SqlDataSource(config=config, db_factory=MagicMock())

    with pytest.raises(DataSourceError, match="not found"):
        source.fetch()


def test_empty_sql_file_raises(tmp_path: Path) -> None:
    """An empty SQL file raises DataSourceError."""
    sql_file = tmp_path / "empty.sql"
    sql_file.write_text("   \n  ", encoding="utf-8")

    config = SqlSourceConfig(
        alias="empty",
        type="sql",
        database_alias="oracle_prod",
        sql_file=str(sql_file),
    )
    source = SqlDataSource(config=config, db_factory=MagicMock())

    with pytest.raises(DataSourceError, match="empty"):
        source.fetch()


def test_database_error_wrapped_in_data_source_error(tmp_path: Path) -> None:
    """A DatabaseError from the connector is re-raised as DataSourceError."""
    source, mock_connector = make_source(tmp_path)
    mock_connector.execute_query.side_effect = DatabaseError("connection refused")

    with pytest.raises(DataSourceError, match="connection refused"):
        source.fetch()


def test_connector_close_called_on_success(tmp_path: Path) -> None:
    """Connector.close() is called after a successful query."""
    source, mock_connector = make_source(tmp_path)
    mock_connector.execute_query.return_value = [{"x": 1}]

    source.fetch()

    mock_connector.close.assert_called_once()


def test_connector_close_called_on_error(tmp_path: Path) -> None:
    """Connector.close() is called even when the query raises an exception."""
    source, mock_connector = make_source(tmp_path)
    mock_connector.execute_query.side_effect = DatabaseError("timeout")

    with pytest.raises(DataSourceError):
        source.fetch()

    mock_connector.close.assert_called_once()
