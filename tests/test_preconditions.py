"""
Tests for preconditions/query_poller.py.

Covers:
  - Precondition passes immediately when query returns a non-null value.
  - Precondition passes after one retry when first query returns null.
  - Precondition exits with code 1 when deadline is already exceeded.
  - Precondition exits with code 1 after retrying past the deadline.
  - SQL file not found → exits with code 1.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from report_runner.config.models import PreconditionConfig
from report_runner.preconditions.query_poller import QueryPollerPreconditionChecker


def make_config(tmp_path: Path, deadline_time: str = "23:59") -> PreconditionConfig:
    """Create a minimal PreconditionConfig with a real SQL file."""
    sql_file = tmp_path / "check.sql"
    sql_file.write_text("SELECT 1 FROM dual", encoding="utf-8")
    return PreconditionConfig(
        type="query_poller",
        description="Test precondition",
        database_alias="oracle_prod",
        sql_file=str(sql_file),
        poll_interval_minutes=1,
        deadline_time=deadline_time,
    )


def make_checker(mock_db_result: object) -> QueryPollerPreconditionChecker:
    """Create a checker whose DB factory always returns the given value."""
    mock_connector = MagicMock()
    mock_connector.execute_query.return_value = [{"result": mock_db_result}]
    mock_connector.close.return_value = None

    mock_factory = MagicMock()
    mock_factory.create.return_value = mock_connector

    return QueryPollerPreconditionChecker(db_factory=mock_factory)


# ── Pass cases ────────────────────────────────────────────────────────────────

def test_passes_immediately_when_value_present(tmp_path: Path) -> None:
    """Precondition passes on the first poll when the query returns a value."""
    config = make_config(tmp_path)
    checker = make_checker("2024-01-15 07:30:00")

    result = checker.check(config)
    assert result is True


def test_passes_after_one_retry(tmp_path: Path) -> None:
    """Precondition passes on the second poll after the first returns None."""
    sql_file = tmp_path / "check.sql"
    sql_file.write_text("SELECT 1", encoding="utf-8")

    config = PreconditionConfig(
        type="query_poller",
        description="Test",
        database_alias="oracle_prod",
        sql_file=str(sql_file),
        poll_interval_minutes=1,
        deadline_time="23:59",
    )

    mock_connector = MagicMock()
    # First call: None (not ready), second call: a value (ready).
    mock_connector.execute_query.side_effect = [
        [{"result": None}],
        [{"result": "done"}],
    ]
    mock_factory = MagicMock()
    mock_factory.create.return_value = mock_connector

    checker = QueryPollerPreconditionChecker(db_factory=mock_factory)

    # Freeze time so deadline is never hit, and patch sleep to be instant.
    future_time = datetime(2099, 1, 1, 6, 0, 0)
    with patch("report_runner.preconditions.query_poller.datetime") as mock_dt:
        mock_dt.now.return_value = future_time
        with patch("report_runner.preconditions.query_poller.time.sleep"):
            result = checker.check(config)

    assert result is True
    assert mock_connector.execute_query.call_count == 2


# ── Deadline exceeded cases ───────────────────────────────────────────────────

def test_exits_when_deadline_already_passed(tmp_path: Path) -> None:
    """If the current time is already past the deadline and query returns null, exit(1)."""
    config = make_config(tmp_path, deadline_time="08:00")
    checker = make_checker(None)  # Query returns null → not ready.

    # Simulate current time as 09:00 (past deadline of 08:00).
    past_deadline = datetime(2024, 1, 15, 9, 0, 0)
    with patch("report_runner.preconditions.query_poller.datetime") as mock_dt:
        mock_dt.now.return_value = past_deadline
        with pytest.raises(SystemExit) as exc_info:
            checker.check(config)

    assert exc_info.value.code == 1


def test_exits_after_retry_hits_deadline(tmp_path: Path) -> None:
    """Precondition retries, then hits the deadline before passing."""
    sql_file = tmp_path / "check.sql"
    sql_file.write_text("SELECT 1", encoding="utf-8")

    config = PreconditionConfig(
        type="query_poller",
        description="Test",
        database_alias="oracle_prod",
        sql_file=str(sql_file),
        poll_interval_minutes=1,
        deadline_time="08:00",
    )

    mock_connector = MagicMock()
    # Both polls return null.
    mock_connector.execute_query.return_value = [{"result": None}]
    mock_factory = MagicMock()
    mock_factory.create.return_value = mock_connector

    checker = QueryPollerPreconditionChecker(db_factory=mock_factory)

    # First poll: 07:58 (before deadline). Second poll: 08:01 (after deadline).
    times = [
        datetime(2024, 1, 15, 7, 58, 0),
        datetime(2024, 1, 15, 8, 1, 0),
    ]
    call_count = [0]

    def mock_now():
        idx = min(call_count[0], len(times) - 1)
        call_count[0] += 1
        return times[idx]

    with patch("report_runner.preconditions.query_poller.datetime") as mock_dt:
        mock_dt.now.side_effect = mock_now
        with patch("report_runner.preconditions.query_poller.time.sleep"):
            with pytest.raises(SystemExit) as exc_info:
                checker.check(config)

    assert exc_info.value.code == 1


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_string_treated_as_not_ready(tmp_path: Path) -> None:
    """An empty string result is treated the same as NULL — not ready."""
    config = make_config(tmp_path, deadline_time="23:59")

    mock_connector = MagicMock()
    mock_connector.execute_query.side_effect = [
        [{"result": ""}],
        [{"result": "complete"}],
    ]
    mock_factory = MagicMock()
    mock_factory.create.return_value = mock_connector
    checker = QueryPollerPreconditionChecker(db_factory=mock_factory)

    future_time = datetime(2099, 1, 1, 6, 0, 0)
    with patch("report_runner.preconditions.query_poller.datetime") as mock_dt:
        mock_dt.now.return_value = future_time
        with patch("report_runner.preconditions.query_poller.time.sleep"):
            result = checker.check(config)

    assert result is True


def test_missing_sql_file_exits(tmp_path: Path) -> None:
    """If the SQL file does not exist, the checker exits with code 1."""
    config = PreconditionConfig(
        type="query_poller",
        description="Test",
        database_alias="oracle_prod",
        sql_file=str(tmp_path / "nonexistent.sql"),
        poll_interval_minutes=1,
        deadline_time="23:59",
    )
    mock_factory = MagicMock()
    checker = QueryPollerPreconditionChecker(db_factory=mock_factory)

    with pytest.raises(SystemExit) as exc_info:
        checker.check(config)

    assert exc_info.value.code == 1
