"""
IdentityTransform — the default transform used when no `transform:` block
is present in the YAML.

It simply passes the single source DataFrame through unchanged.  Having this
explicit class (instead of an if/else in the orchestrator) keeps the execution
path uniform: every report always goes through a TransformStep.
"""

from __future__ import annotations

import pandas as pd

from report_runner.transforms.base import TransformError, TransformStep


class IdentityTransform(TransformStep):
    """
    Returns the sole input DataFrame unchanged.

    Raises TransformError if more than one source is provided — the caller
    should use a real transform function for multi-source reports.
    """

    def apply(self, sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
        if len(sources) != 1:
            raise TransformError(
                f"IdentityTransform requires exactly 1 source, "
                f"but {len(sources)} were provided: {list(sources.keys())}. "
                f"Add a 'transform:' block to the report config for multi-source reports."
            )
        # Return the single value regardless of its alias key.
        return next(iter(sources.values()))
