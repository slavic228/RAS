"""
Abstract base class for exporters.

An Exporter takes the collected report results and workbook grouping config,
writes output files to disk, and returns a list of ExportedFile objects that
the distribution phase uses to attach files to emails.

The Exporter has no knowledge of recipients or email logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from report_runner.config.models import WorkbookGroup
from report_runner.models import ExportedFile, ReportResult


class Exporter(ABC):
    """Writes report data to output files and returns metadata about what was written."""

    @abstractmethod
    def export(
        self,
        groups: list[WorkbookGroup],
        results: list[ReportResult],
        output_dir: str,
    ) -> list[ExportedFile]:
        """
        Export the results and return the list of files created.

        Args:
            groups:     Workbook grouping config from the YAML outputs block.
            results:    All report results from the execution phase.
            output_dir: Target directory path (may contain {date} placeholder).

        Returns:
            A list of ExportedFile objects, each carrying the file path and
            the report names it contains.
        """
        ...
