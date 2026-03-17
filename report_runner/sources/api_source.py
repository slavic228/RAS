"""
REST API data source.

Makes a synchronous HTTP GET or POST request using httpx, optionally applies
a JSONPath expression to extract a nested array from the response, and returns
the result as a pandas DataFrame.

Supports:
  - GET and POST methods
  - Custom headers (values interpolated from .env at config load time)
  - Optional JSON body for POST requests
  - JSONPath extraction of the target array from the response body
  - Configurable timeout
"""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd
from jsonpath_ng import parse as jsonpath_parse
from loguru import logger

from report_runner.config.models import ApiSourceConfig
from report_runner.sources.base import DataSource, DataSourceError


class ApiDataSource(DataSource):
    """Fetches data from a REST endpoint and converts the result to a DataFrame."""

    def __init__(self, config: ApiSourceConfig) -> None:
        self._config = config

    def fetch(self) -> pd.DataFrame:
        logger.debug(
            "ApiDataSource: {} {} (alias '{}')",
            self._config.method,
            self._config.url,
            self._config.alias,
        )

        response_data = self._make_request()
        extracted = self._extract_data(response_data)

        if not isinstance(extracted, list):
            raise DataSourceError(
                f"API source '{self._config.alias}': expected a JSON array after "
                f"applying response_path '{self._config.response_path}', "
                f"got {type(extracted).__name__}."
            )

        df = pd.DataFrame(extracted)
        logger.debug(
            "ApiDataSource: '{}' returned {} rows.",
            self._config.alias,
            len(df),
        )
        return df

    # ── Private helpers ───────────────────────────────────────────────────────

    def _make_request(self) -> Any:
        """Execute the HTTP request and return the parsed JSON body."""
        timeout = self._config.timeout_seconds

        try:
            with httpx.Client(timeout=timeout) as client:
                if self._config.method == "GET":
                    response = client.get(
                        self._config.url,
                        headers=self._config.headers,
                    )
                else:  # POST
                    response = client.post(
                        self._config.url,
                        headers=self._config.headers,
                        json=self._config.body,
                    )
        except httpx.TimeoutException as exc:
            raise DataSourceError(
                f"API source '{self._config.alias}': request timed out after "
                f"{timeout}s — {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise DataSourceError(
                f"API source '{self._config.alias}': network error — {exc}"
            ) from exc

        if response.is_error:
            raise DataSourceError(
                f"API source '{self._config.alias}': HTTP {response.status_code} "
                f"from {self._config.url}."
            )

        try:
            return response.json()
        except Exception as exc:
            raise DataSourceError(
                f"API source '{self._config.alias}': could not parse JSON response — {exc}"
            ) from exc

    def _extract_data(self, response_data: Any) -> Any:
        """Apply the JSONPath expression if configured, else return the data as-is."""
        if not self._config.response_path:
            return response_data

        expression = jsonpath_parse(self._config.response_path)
        matches = expression.find(response_data)

        if not matches:
            raise DataSourceError(
                f"API source '{self._config.alias}': JSONPath '{self._config.response_path}' "
                f"matched nothing in the response."
            )

        # find() returns a list of Match objects; we want the first match's value.
        return matches[0].value
