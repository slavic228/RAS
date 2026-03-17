"""
WorkflowRunner — the top-level coordinator.

Executes exactly these phases in order:
  1. PRECONDITIONS  — blocks until all pass or deadline is exceeded
  2. EXECUTION      — runs each report serially, respects on_failure policy
  3. EXPORT         — writes .xlsx files to disk
  4. DISTRIBUTION   — sends emails per notification block
  5. EXIT           — returns the appropriate exit code

Design principles:
  - No knowledge of DB types, API details, transform logic, or SMTP internals.
  - Calls only abstract interfaces.
  - Branching on `on_failure` is the only policy decision made here.
  - Partial results (from an abort) are still exported and distributed.
"""

from __future__ import annotations

from datetime import date, datetime

from loguru import logger

from report_runner.config.models import (
    EmailNotificationConfig,
    ExcelOutputConfig,
    PreconditionConfig,
    WorkflowConfig,
)
from report_runner.exporters.base import Exporter
from report_runner.models import ExportedFile, NotificationContext, ReportResult
from report_runner.notifications.base import Notifier
from report_runner.preconditions.base import PreconditionChecker
from report_runner.reports.base import ReportRunner


class WorkflowRunner:
    """
    Coordinates the four phases of a workflow run.

    All dependencies are injected via the constructor so the orchestrator
    itself is easy to unit-test with mocks.
    """

    def __init__(
        self,
        precondition_checker: PreconditionChecker,
        report_runner: ReportRunner,
        exporter: Exporter,
        notifier: Notifier,
    ) -> None:
        self._precondition_checker = precondition_checker
        self._report_runner = report_runner
        self._exporter = exporter
        self._notifier = notifier

    def run(self, config: WorkflowConfig) -> int:
        """
        Execute the full workflow.

        Returns:
            0  — all reports succeeded, all emails sent.
            1  — precondition deadline exceeded (this path calls sys.exit, not return).
            2  — one or more reports failed (partial success).
            3  — unrecoverable configuration or infrastructure error.
        """
        run_started_at = datetime.now()
        logger.info("=" * 60)
        logger.info("Workflow '{}' started at {}", config.name, run_started_at)
        logger.info("=" * 60)

        # ── Phase 1: Preconditions ────────────────────────────────────────────
        self._run_preconditions(config)

        # ── Phase 2: Execution ────────────────────────────────────────────────
        results = self._run_reports(config)

        # ── Phase 3: Export ───────────────────────────────────────────────────
        exported_files = self._run_export(config, results)

        # ── Phase 4: Distribution ─────────────────────────────────────────────
        self._run_distribution(config, results, exported_files, run_started_at)

        # ── Phase 5: Exit code ────────────────────────────────────────────────
        exit_code = self._determine_exit_code(results)
        logger.info(
            "Workflow '{}' finished. Exit code: {}",
            config.name,
            exit_code,
        )
        return exit_code

    # ── Phase implementations ─────────────────────────────────────────────────

    def _run_preconditions(self, config: WorkflowConfig) -> None:
        if not config.preconditions:
            return

        logger.info("Phase 1/4: Evaluating {} precondition(s)...", len(config.preconditions))
        for precondition in config.preconditions:
            # check() either returns True or calls sys.exit(1).
            self._precondition_checker.check(precondition)

        logger.info("All preconditions passed.")

    def _run_reports(self, config: WorkflowConfig) -> list[ReportResult]:
        logger.info("Phase 2/4: Executing {} report(s)...", len(config.reports))
        results: list[ReportResult] = []

        for report_config in config.reports:
            logger.info("Running report: '{}'", report_config.name)
            started_at = datetime.now()

            try:
                df = self._report_runner.run(report_config)
                finished_at = datetime.now()
                row_count = len(df)
                result = ReportResult(
                    report_name=report_config.name,
                    status="success",
                    dataframe=df,
                    row_count=row_count,
                    started_at=started_at,
                    finished_at=finished_at,
                )
                logger.info(
                    "Report '{}' succeeded: {} rows in {:.1f}s.",
                    report_config.name,
                    row_count,
                    (finished_at - started_at).total_seconds(),
                )

            except Exception as exc:
                finished_at = datetime.now()
                result = ReportResult(
                    report_name=report_config.name,
                    status="failed",
                    dataframe=None,
                    row_count=0,
                    started_at=started_at,
                    finished_at=finished_at,
                    error_message=str(exc),
                )

                if report_config.on_failure == "abort":
                    logger.exception(
                        "Report '{}' FAILED (on_failure=abort). "
                        "Stopping execution. Partial results will still be exported.",
                        report_config.name,
                    )
                    results.append(result)
                    break  # Stop the execution loop; proceed to export.
                else:  # skip
                    logger.warning(
                        "Report '{}' FAILED (on_failure=skip). Continuing.",
                        report_config.name,
                    )
                    logger.exception("Report failure details:")

            results.append(result)

        return results

    def _run_export(
        self,
        config: WorkflowConfig,
        results: list[ReportResult],
    ) -> list[ExportedFile]:
        logger.info("Phase 3/4: Exporting results...")

        all_exported: list[ExportedFile] = []

        for output_config in config.outputs:
            if isinstance(output_config, ExcelOutputConfig):
                exported = self._exporter.export(
                    groups=output_config.workbook_groups,
                    results=results,
                    output_dir=output_config.output_dir,
                )
                all_exported.extend(exported)

        if not config.outputs:
            logger.warning("No outputs configured — skipping export phase.")

        return all_exported

    def _run_distribution(
        self,
        config: WorkflowConfig,
        results: list[ReportResult],
        exported_files: list[ExportedFile],
        run_started_at: datetime,
    ) -> None:
        if not config.notifications:
            logger.info("No notifications configured — skipping distribution phase.")
            return

        logger.info(
            "Phase 4/4: Sending {} notification(s)...",
            len(config.notifications),
        )

        run_date = date.today()
        results_by_name = {r.report_name: r for r in results}

        for notification_config in config.notifications:
            # Filter results to only the reports this block cares about.
            scoped_results = [
                results_by_name[name]
                for name in notification_config.reports
                if name in results_by_name
            ]

            # Filter files: keep only files that contain at least one of this
            # block's reports.
            scoped_report_names = set(notification_config.reports)
            scoped_files = [
                f for f in exported_files
                if scoped_report_names.intersection(f.report_names)
            ]

            context = NotificationContext(
                workflow_name=config.name,
                run_date=run_date,
                run_started_at=run_started_at,
                results=scoped_results,
                attached_files=scoped_files,
            )

            try:
                self._notifier.notify(context, notification_config)
            except Exception as exc:
                # Defensive: catch any exception that leaked out of the notifier
                # so that the next notification block is always attempted.
                logger.exception(
                    "Unexpected error in notifier for recipients {}: {}",
                    notification_config.to,
                    exc,
                )

    @staticmethod
    def _determine_exit_code(results: list[ReportResult]) -> int:
        """
        Exit codes:
          0 — all reports succeeded.
          2 — at least one report failed.
        """
        if any(r.status == "failed" for r in results):
            return 2
        return 0
