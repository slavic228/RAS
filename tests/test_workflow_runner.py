"""
Tests for orchestrator/workflow_runner.py.

Covers:
  - All phases execute in order (preconditions → execution → export → distribution).
  - on_failure=abort stops execution but still exports and notifies partial results.
  - on_failure=skip logs and continues to subsequent reports.
  - All notification blocks are attempted even after one fails.
  - Distribution filtering: each notification receives only its scoped reports/files.
  - Exit code is 0 when all reports succeed.
  - Exit code is 2 when at least one report fails.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from report_runner.config.models import (
    EmailNotificationConfig,
    ExcelOutputConfig,
    ReportConfig,
    SqlSourceConfig,
    WorkbookGroup,
    WorkflowConfig,
)
from report_runner.models import ExportedFile, ReportResult
from report_runner.orchestrator.workflow_runner import WorkflowRunner


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_report_config(name: str, on_failure: str = "skip") -> ReportConfig:
    return ReportConfig(
        name=name,
        on_failure=on_failure,  # type: ignore[arg-type]
        sources=[
            SqlSourceConfig(
                alias="s",
                type="sql",
                database_alias="oracle_prod",
                sql_file="query.sql",
            )
        ],
    )


def make_workflow(
    reports: list[ReportConfig],
    notifications: list[EmailNotificationConfig] | None = None,
    outputs: list[ExcelOutputConfig] | None = None,
) -> WorkflowConfig:
    return WorkflowConfig(
        name="Test Workflow",
        reports=reports,
        notifications=notifications or [],
        outputs=outputs or [],
    )


def make_runner(
    report_results: list[pd.DataFrame | Exception],
    exported_files: list[ExportedFile] | None = None,
) -> tuple[WorkflowRunner, MagicMock, MagicMock, MagicMock, MagicMock]:
    """Create a WorkflowRunner with mocked collaborators."""
    mock_precondition = MagicMock()
    mock_precondition.check.return_value = True

    mock_report_runner = MagicMock()
    side_effects = []
    for result in report_results:
        if isinstance(result, Exception):
            side_effects.append(result)
        else:
            side_effects.append(result)
    mock_report_runner.run.side_effect = side_effects

    mock_exporter = MagicMock()
    mock_exporter.export.return_value = exported_files or []

    mock_notifier = MagicMock()

    runner = WorkflowRunner(
        precondition_checker=mock_precondition,
        report_runner=mock_report_runner,
        exporter=mock_exporter,
        notifier=mock_notifier,
    )
    return runner, mock_precondition, mock_report_runner, mock_exporter, mock_notifier


# ── Exit code tests ───────────────────────────────────────────────────────────

def test_exit_code_0_when_all_succeed() -> None:
    """Returns 0 when all reports succeed."""
    config = make_workflow([make_report_config("R1"), make_report_config("R2")])
    runner, *_ = make_runner([pd.DataFrame({"a": [1]}), pd.DataFrame({"b": [2]})])

    exit_code = runner.run(config)
    assert exit_code == 0


def test_exit_code_2_when_any_report_fails() -> None:
    """Returns 2 when at least one report fails (on_failure=skip)."""
    config = make_workflow([make_report_config("R1"), make_report_config("R2", "skip")])
    runner, *_ = make_runner([
        pd.DataFrame({"a": [1]}),
        RuntimeError("DB error"),
    ])

    exit_code = runner.run(config)
    assert exit_code == 2


# ── on_failure=abort tests ────────────────────────────────────────────────────

def test_abort_stops_execution_after_failure() -> None:
    """on_failure=abort stops the execution loop after the failing report."""
    r1 = make_report_config("R1", "abort")
    r2 = make_report_config("R2", "skip")
    r3 = make_report_config("R3", "skip")

    config = make_workflow([r1, r2, r3])
    runner, _, mock_report, mock_exporter, _ = make_runner([
        RuntimeError("R1 failed"),
    ])

    runner.run(config)

    # Only R1 was attempted (R2 and R3 were skipped due to abort).
    assert mock_report.run.call_count == 1


def test_abort_still_exports_partial_results() -> None:
    """After abort, the exporter is still called with the partial results."""
    r1 = make_report_config("R1", "abort")
    r2 = make_report_config("R2", "skip")

    config = make_workflow(
        reports=[r1, r2],
        outputs=[ExcelOutputConfig(type="excel", output_dir="output")],
    )
    runner, _, mock_report, mock_exporter, _ = make_runner([
        RuntimeError("R1 failed"),
    ])

    runner.run(config)

    mock_exporter.export.assert_called_once()
    # The results passed to export should contain R1 (as failed).
    call_results = mock_exporter.export.call_args.kwargs["results"]
    assert len(call_results) == 1
    assert call_results[0].report_name == "R1"
    assert call_results[0].status == "failed"


def test_abort_still_notifies_partial_results() -> None:
    """After abort, the notifier is still called with partial results."""
    r1 = make_report_config("R1", "abort")

    notification = EmailNotificationConfig(
        type="email",
        smtp_alias="smtp_corp",
        to=["user@example.com"],
        subject="Test",
        body_template="templates/email.j2",
        reports=["R1"],
    )

    config = make_workflow(reports=[r1], notifications=[notification])
    runner, _, _, _, mock_notifier = make_runner([RuntimeError("fail")])

    runner.run(config)

    mock_notifier.notify.assert_called_once()


# ── on_failure=skip tests ─────────────────────────────────────────────────────

def test_skip_continues_to_next_report() -> None:
    """on_failure=skip logs the error and continues running subsequent reports."""
    r1 = make_report_config("R1", "skip")
    r2 = make_report_config("R2", "skip")

    config = make_workflow([r1, r2])
    runner, _, mock_report, _, _ = make_runner([
        RuntimeError("R1 failed"),
        pd.DataFrame({"x": [1]}),
    ])

    runner.run(config)

    assert mock_report.run.call_count == 2


# ── Distribution filtering tests ──────────────────────────────────────────────

def test_distribution_filters_results_per_notification() -> None:
    """Each notification block only receives results for its own reports."""
    r1 = make_report_config("Report A")
    r2 = make_report_config("Report B")

    notification_a = EmailNotificationConfig(
        type="email",
        smtp_alias="smtp_corp",
        to=["a@example.com"],
        subject="A",
        body_template="templates/t.j2",
        reports=["Report A"],
    )
    notification_ab = EmailNotificationConfig(
        type="email",
        smtp_alias="smtp_corp",
        to=["b@example.com"],
        subject="AB",
        body_template="templates/t.j2",
        reports=["Report A", "Report B"],
    )

    config = make_workflow(
        reports=[r1, r2],
        notifications=[notification_a, notification_ab],
    )
    runner, _, _, _, mock_notifier = make_runner([
        pd.DataFrame({"a": [1]}),
        pd.DataFrame({"b": [2]}),
    ])

    runner.run(config)

    assert mock_notifier.notify.call_count == 2

    # First call: only Report A.
    first_context = mock_notifier.notify.call_args_list[0].args[0]
    assert len(first_context.results) == 1
    assert first_context.results[0].report_name == "Report A"

    # Second call: both reports.
    second_context = mock_notifier.notify.call_args_list[1].args[0]
    assert len(second_context.results) == 2


def test_distribution_filters_attachments_per_notification() -> None:
    """Each notification receives only files containing its reports."""
    r1 = make_report_config("Report A")
    r2 = make_report_config("Report B")

    notification_a_only = EmailNotificationConfig(
        type="email",
        smtp_alias="smtp_corp",
        to=["a@example.com"],
        subject="A Only",
        body_template="templates/t.j2",
        reports=["Report A"],
    )

    # Two exported files: one with Report A, one with Report B.
    file_a = ExportedFile(path=Path("file_a.xlsx"), report_names=["Report A"])
    file_b = ExportedFile(path=Path("file_b.xlsx"), report_names=["Report B"])

    config = make_workflow(
        reports=[r1, r2],
        notifications=[notification_a_only],
        outputs=[ExcelOutputConfig(type="excel", output_dir="output")],
    )
    runner, _, _, mock_exporter, mock_notifier = make_runner(
        [pd.DataFrame({"a": [1]}), pd.DataFrame({"b": [2]})],
        exported_files=[file_a, file_b],
    )

    runner.run(config)

    context = mock_notifier.notify.call_args.args[0]
    # Only file_a should be attached (contains Report A).
    assert len(context.attached_files) == 1
    assert context.attached_files[0].path == Path("file_a.xlsx")


# ── Notification resilience ───────────────────────────────────────────────────

def test_all_notifications_attempted_even_after_one_fails() -> None:
    """A notification failure does not prevent subsequent notification blocks from running."""
    r1 = make_report_config("R1")

    n1 = EmailNotificationConfig(
        type="email", smtp_alias="smtp_corp", to=["a@a.com"],
        subject="A", body_template="t.j2", reports=["R1"],
    )
    n2 = EmailNotificationConfig(
        type="email", smtp_alias="smtp_corp", to=["b@b.com"],
        subject="B", body_template="t.j2", reports=["R1"],
    )

    config = make_workflow(reports=[r1], notifications=[n1, n2])
    runner, _, _, _, mock_notifier = make_runner([pd.DataFrame({"x": [1]})])

    # First notification raises; second should still be called.
    mock_notifier.notify.side_effect = [Exception("SMTP error"), None]

    # The runner should not propagate the exception.
    exit_code = runner.run(config)

    assert mock_notifier.notify.call_count == 2
    assert exit_code == 0
