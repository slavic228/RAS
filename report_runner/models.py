"""
Runtime data models shared across the execution, export, and distribution phases.

These are distinct from config/models.py (which models the YAML schema).
These models represent the *output* of each phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel


@dataclass
class ReportResult:
    """Holds the outcome of running a single report."""

    report_name: str
    status: Literal["success", "failed", "skipped"]
    dataframe: pd.DataFrame | None
    row_count: int
    started_at: datetime
    finished_at: datetime
    error_message: str | None = None


@dataclass
class ExportedFile:
    """
    Represents a single .xlsx file written to disk.

    `report_names` lists which report names appear as sheets in this file.
    The distribution phase uses this list to decide which files to attach
    to each notification email.
    """

    path: Path
    report_names: list[str] = field(default_factory=list)


class NotificationContext(BaseModel):
    """
    All data the email template and notifier need for one notification block.

    The orchestrator builds this object after filtering results and files to
    the scope of a single notification block.
    """

    workflow_name: str
    run_date: date
    run_started_at: datetime
    results: list[ReportResult]          # filtered to this notification's reports
    attached_files: list[ExportedFile]   # filtered to this notification's reports

    model_config = {"arbitrary_types_allowed": True}
