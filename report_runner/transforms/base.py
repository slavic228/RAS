"""
Abstract base class for transform steps.

A TransformStep takes a dict of DataFrames (keyed by source alias) and
produces a single merged/transformed DataFrame.  It is the bridge between
the data fetching phase and the export phase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class TransformStep(ABC):
    """Merges or transforms a collection of source DataFrames into one."""

    @abstractmethod
    def apply(self, sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Apply the transformation and return the final DataFrame.

        Args:
            sources: Mapping of source alias → DataFrame as produced by
                     DataSource.fetch() calls.

        Returns:
            A single DataFrame ready for export.
        """
        ...


class TransformError(Exception):
    """Raised when a transform function fails or has an invalid signature."""
