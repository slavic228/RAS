"""
Abstract base class for report runners.

A ReportRunner takes a ReportConfig and produces a DataFrame (or raises
on unrecoverable failure).  The orchestrator calls .run() without knowing
anything about how data is fetched or transformed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from report_runner.config.models import ReportConfig


class ReportRunner(ABC):
    """Executes a report and returns the result as a DataFrame."""

    @abstractmethod
    def run(self, config: ReportConfig) -> pd.DataFrame:
        """
        Run the report and return a DataFrame.

        Raises any exception on unrecoverable failure; the orchestrator
        handles the on_failure policy (skip vs abort).
        """
        ...
