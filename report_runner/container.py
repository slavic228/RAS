"""
Dependency Injection container (dependency-injector library).

This is the single place where concrete implementations are bound to
abstract interfaces.  All other modules receive their dependencies via
constructor injection and never instantiate their own collaborators.

Container structure mirrors the dependency graph:
  DatabaseConnectorFactory
    └─ DataSourceFactory
         └─ CompositeReportRunner ←─ TransformLoader
  ExcelExporter
  EmailNotifier
  QueryPollerPreconditionChecker
    └─ WorkflowRunner (receives all of the above)
"""

from __future__ import annotations

from dependency_injector import containers, providers

from report_runner.database.factory import DatabaseConnectorFactory
from report_runner.exporters.excel_exporter import ExcelExporter
from report_runner.notifications.email_notifier import EmailNotifier
from report_runner.orchestrator.workflow_runner import WorkflowRunner
from report_runner.preconditions.query_poller import QueryPollerPreconditionChecker
from report_runner.reports.composite_report import CompositeReportRunner
from report_runner.sources.factory import DataSourceFactory
from report_runner.transforms.loader import TransformLoader


class ApplicationContainer(containers.DeclarativeContainer):
    """
    Wires all application components together.

    Each provider is a Factory (creates a new instance on demand) rather
    than a Singleton, which makes the container easier to test and avoids
    hidden shared state.  The WorkflowRunner itself is long-lived, but its
    collaborators are lightweight enough that re-creation is not a concern.
    """

    # ── Infrastructure ────────────────────────────────────────────────────────

    db_factory = providers.Factory(DatabaseConnectorFactory)

    # ── Data layer ────────────────────────────────────────────────────────────

    source_factory = providers.Factory(
        DataSourceFactory,
        db_factory=db_factory,
    )

    transform_loader = providers.Factory(TransformLoader)

    # ── Report layer ──────────────────────────────────────────────────────────

    report_runner = providers.Factory(
        CompositeReportRunner,
        source_factory=source_factory,
        transform_loader=transform_loader,
    )

    # ── Export layer ──────────────────────────────────────────────────────────

    exporter = providers.Factory(ExcelExporter)

    # ── Notification layer ────────────────────────────────────────────────────

    notifier = providers.Factory(EmailNotifier)

    # ── Preconditions ─────────────────────────────────────────────────────────

    precondition_checker = providers.Factory(
        QueryPollerPreconditionChecker,
        db_factory=db_factory,
    )

    # ── Orchestrator ──────────────────────────────────────────────────────────

    workflow_runner = providers.Factory(
        WorkflowRunner,
        precondition_checker=precondition_checker,
        report_runner=report_runner,
        exporter=exporter,
        notifier=notifier,
    )
