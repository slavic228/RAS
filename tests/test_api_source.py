"""
Tests for sources/api_source.py.

Covers:
  - GET request with JSONPath extraction returns correct DataFrame.
  - GET request without response_path uses full response.
  - POST request is sent with JSON body.
  - HTTP 4xx/5xx raises DataSourceError.
  - Timeout raises DataSourceError.
  - JSONPath that matches nothing raises DataSourceError.
  - JSONPath that returns non-list raises DataSourceError.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import httpx

from report_runner.config.models import ApiSourceConfig
from report_runner.sources.api_source import ApiDataSource
from report_runner.sources.base import DataSourceError


def make_config(**kwargs) -> ApiSourceConfig:
    """Create an ApiSourceConfig with sensible defaults."""
    defaults = {
        "alias": "test_api",
        "type": "api",
        "url": "https://api.example.com/data",
        "method": "GET",
        "timeout_seconds": 30,
    }
    defaults.update(kwargs)
    return ApiSourceConfig(**defaults)


def make_mock_response(body: object, status_code: int = 200) -> MagicMock:
    """Create a mock httpx Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.is_error = status_code >= 400
    mock_resp.json.return_value = body
    return mock_resp


# ── Success cases ─────────────────────────────────────────────────────────────

def test_get_with_jsonpath_returns_dataframe() -> None:
    """GET + JSONPath extracts the nested array and returns a DataFrame."""
    response_body = {"rates": [{"currency": "USD", "rate": 1.0}, {"currency": "EUR", "rate": 0.9}]}
    config = make_config(response_path="$.rates")

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = make_mock_response(response_body)

    with patch("report_runner.sources.api_source.httpx.Client", return_value=mock_client):
        df = ApiDataSource(config).fetch()

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert "currency" in df.columns
    assert "rate" in df.columns


def test_get_without_jsonpath_uses_full_response() -> None:
    """GET without response_path treats the full array response as the data."""
    response_body = [{"id": 1}, {"id": 2}]
    config = make_config()  # no response_path

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = make_mock_response(response_body)

    with patch("report_runner.sources.api_source.httpx.Client", return_value=mock_client):
        df = ApiDataSource(config).fetch()

    assert len(df) == 2


def test_post_sends_json_body() -> None:
    """POST request sends the configured body and returns a DataFrame."""
    response_body = [{"result": "ok"}]
    config = make_config(method="POST", body={"filter": "today"})

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = make_mock_response(response_body)

    with patch("report_runner.sources.api_source.httpx.Client", return_value=mock_client):
        df = ApiDataSource(config).fetch()

    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs["json"] == {"filter": "today"}
    assert len(df) == 1


# ── Error cases ───────────────────────────────────────────────────────────────

def test_http_error_raises_data_source_error() -> None:
    """A non-2xx HTTP response raises DataSourceError."""
    config = make_config()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = make_mock_response({}, status_code=503)

    with patch("report_runner.sources.api_source.httpx.Client", return_value=mock_client):
        with pytest.raises(DataSourceError, match="HTTP 503"):
            ApiDataSource(config).fetch()


def test_timeout_raises_data_source_error() -> None:
    """A timeout exception is wrapped in DataSourceError."""
    config = make_config()

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = httpx.TimeoutException("timed out")

    with patch("report_runner.sources.api_source.httpx.Client", return_value=mock_client):
        with pytest.raises(DataSourceError, match="timed out"):
            ApiDataSource(config).fetch()


def test_jsonpath_no_match_raises_data_source_error() -> None:
    """A JSONPath expression that matches nothing raises DataSourceError."""
    response_body = {"data": [{"x": 1}]}
    config = make_config(response_path="$.nonexistent_key")

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = make_mock_response(response_body)

    with patch("report_runner.sources.api_source.httpx.Client", return_value=mock_client):
        with pytest.raises(DataSourceError, match="matched nothing"):
            ApiDataSource(config).fetch()


def test_jsonpath_returns_non_list_raises() -> None:
    """JSONPath returning a dict (not a list) raises DataSourceError."""
    response_body = {"meta": {"count": 5}}
    config = make_config(response_path="$.meta")

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = make_mock_response(response_body)

    with patch("report_runner.sources.api_source.httpx.Client", return_value=mock_client):
        with pytest.raises(DataSourceError, match="expected a JSON array"):
            ApiDataSource(config).fetch()
