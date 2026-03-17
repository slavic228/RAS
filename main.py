"""
CLI entrypoint — dependency injection wiring only, zero business logic.

Usage:
    python main.py --workflow path/to/workflow.yaml
    python main.py --workflow path/to/workflow.yaml --dry-run
    python main.py --workflow path/to/workflow.yaml --log-level DEBUG

Exit codes:
    0  All reports succeeded, all emails sent.
    1  Precondition deadline exceeded.
    2  One or more reports failed (partial success), emails still sent.
    3  Unrecoverable error (invalid YAML, missing .env key, bad transform).
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report automation runner — executes a YAML workflow file."
    )
    parser.add_argument(
        "--workflow",
        required=True,
        metavar="PATH",
        help="Path to the .yaml workflow file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate YAML and print execution plan without running any queries.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Override the LOG_LEVEL from .env.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # Load .env before importing any module that reads os.environ.
    load_dotenv(override=False)

    # Deferred imports so dotenv is loaded before any module reads env vars.
    from report_runner.config.loader import load_workflow
    from report_runner.config.models import ConfigurationError
    from report_runner.container import ApplicationContainer
    from report_runner.logging_setup.setup import configure_logging

    try:
        workflow_config = load_workflow(args.workflow)
    except ConfigurationError as exc:
        # Print to stderr before logging is set up.
        print(f"[ERROR] Configuration error: {exc}", file=sys.stderr)
        sys.exit(3)

    # Configure logging using the workflow name (available after YAML is parsed).
    configure_logging(workflow_config.name, log_level_override=args.log_level)

    if args.dry_run:
        _print_dry_run_plan(workflow_config)
        sys.exit(0)

    # Wire the DI container and run.
    container = ApplicationContainer()
    runner = container.workflow_runner()

    try:
        exit_code = runner.run(workflow_config)
    except SystemExit:
        # SystemExit is raised by precondition checker on deadline (exit code 1).
        raise
    except Exception as exc:
        from loguru import logger
        logger.exception("Unrecoverable error during workflow execution: {}", exc)
        sys.exit(3)

    sys.exit(exit_code)


def _print_dry_run_plan(workflow_config: object) -> None:
    """Print a human-readable summary of what the workflow would execute."""
    from report_runner.config.models import WorkflowConfig
    assert isinstance(workflow_config, WorkflowConfig)

    print(f"\n{'=' * 60}")
    print(f"DRY RUN — Workflow: {workflow_config.name}")
    print(f"{'=' * 60}")

    if workflow_config.description:
        print(f"Description: {workflow_config.description}")

    print(f"\nPreconditions ({len(workflow_config.preconditions)}):")
    for pc in workflow_config.preconditions:
        print(f"  [{pc.type}] {pc.description} (deadline: {pc.deadline_time})")

    print(f"\nReports ({len(workflow_config.reports)}):")
    for r in workflow_config.reports:
        sources_summary = ", ".join(
            f"{s.alias}({s.type})" for s in r.sources
        )
        transform_summary = (
            f"{r.transform.module}.{r.transform.function}"
            if r.transform else "IdentityTransform"
        )
        print(f"  [{r.on_failure:5}] {r.name}")
        print(f"           sources: {sources_summary}")
        print(f"           transform: {transform_summary}")

    print(f"\nOutputs ({len(workflow_config.outputs)}):")
    for o in workflow_config.outputs:
        print(f"  [{o.type}] {o.output_dir}")

    print(f"\nNotifications ({len(workflow_config.notifications)}):")
    for n in workflow_config.notifications:
        print(f"  [{n.type}] to={n.to}, reports={n.reports}")

    print(f"\n{'=' * 60}")
    print("Dry run complete — no database or API calls were made.")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
