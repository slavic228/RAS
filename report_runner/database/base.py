"""
Abstract base class for all database connectors.

Every concrete connector (Oracle, MSSQL, PostgreSQL) must implement this
interface.  The rest of the codebase depends only on this abstraction —
never on a specific DB driver.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DatabaseConnector(ABC):
    """Thin abstraction over a raw database connection."""

    @abstractmethod
    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        """
        Execute a SQL string and return all rows as a list of dicts.

        Each dict maps column name → value for one row.
        Raises DatabaseError on any driver-level failure.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Release the underlying connection back to the pool or close it."""
        ...


class DatabaseError(Exception):
    """Raised by connectors when a query or connection operation fails."""
