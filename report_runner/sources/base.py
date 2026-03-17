"""
Abstract base class for all data sources.

A DataSource encapsulates everything needed to produce a DataFrame from
one external system (a database query, an API call, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class DataSource(ABC):
    """Fetches data from a single external source and returns it as a DataFrame."""

    @abstractmethod
    def fetch(self) -> pd.DataFrame:
        """
        Execute the data retrieval and return the result as a DataFrame.

        Raises DataSourceError on any retrieval failure.
        """
        ...


class DataSourceError(Exception):
    """Raised by DataSource.fetch() on any retrieval failure."""
