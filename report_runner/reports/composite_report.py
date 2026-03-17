"""
CompositeReportRunner — the single ReportRunner implementation.

Execution path (identical for every report, simple or complex):
  1. For each source in config.sources:
       DataSourceFactory.create(source_config) → DataSource
       DataSource.fetch() → DataFrame
       Stored as sources_dict[alias] = DataFrame
  2. If a transform block is defined:
       TransformLoader.load(module, function) → callable
       PythonFunctionTransform(fn).apply(sources_dict) → final DataFrame
     Else:
       IdentityTransform().apply(sources_dict) → single DataFrame
  3. Return the final DataFrame.

The orchestrator never branches on report type.  Every report travels this
exact path — the IdentityTransform makes single-source reports a special
case of the general pattern, not a separate code path.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
from loguru import logger

from report_runner.config.models import ReportConfig
from report_runner.reports.base import ReportRunner
from report_runner.sources.factory import DataSourceFactory
from report_runner.transforms.base import TransformStep
from report_runner.transforms.identity import IdentityTransform
from report_runner.transforms.loader import TransformLoader


class PythonFunctionTransform(TransformStep):
    """
    Wraps an arbitrary Python callable into the TransformStep interface.

    This thin adapter lets the loader return a raw callable while the
    orchestrator always works with the TransformStep abstraction.
    """

    def __init__(self, fn: Callable[[dict[str, pd.DataFrame]], pd.DataFrame]) -> None:
        self._fn = fn

    def apply(self, sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self._fn(sources)


class CompositeReportRunner(ReportRunner):
    """
    Runs any report by composing DataSources through a TransformStep.

    Receives its dependencies via constructor injection — it never creates
    its own database connections or imports transform modules.
    """

    def __init__(
        self,
        source_factory: DataSourceFactory,
        transform_loader: TransformLoader,
    ) -> None:
        self._source_factory = source_factory
        self._transform_loader = transform_loader

    def run(self, config: ReportConfig) -> pd.DataFrame:
        # ── Phase 1: Fetch all sources ────────────────────────────────────────
        sources_dict: dict[str, pd.DataFrame] = {}
        for source_config in config.sources:
            logger.info(
                "  Fetching source '{}' (type: {})",
                source_config.alias,
                source_config.type,
            )
            source = self._source_factory.create(source_config)
            df = source.fetch()
            sources_dict[source_config.alias] = df
            logger.info(
                "  Source '{}' fetched: {} rows, {} columns.",
                source_config.alias,
                len(df),
                len(df.columns),
            )

        # ── Phase 2: Apply transform ──────────────────────────────────────────
        transform = self._resolve_transform(config)
        logger.info(
            "  Applying transform: {}",
            type(transform).__name__,
        )
        result_df = transform.apply(sources_dict)
        logger.info(
            "  Transform complete: {} rows, {} columns.",
            len(result_df),
            len(result_df.columns),
        )

        return result_df

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_transform(self, config: ReportConfig) -> TransformStep:
        """Return the appropriate TransformStep for this report config."""
        if config.transform is None:
            return IdentityTransform()

        fn = self._transform_loader.load(
            config.transform.module,
            config.transform.function,
        )
        return PythonFunctionTransform(fn)
