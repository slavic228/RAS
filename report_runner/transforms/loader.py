"""
TransformLoader — loads user-defined transform functions by module path.

Responsibilities:
  1. Import the module dynamically using importlib.
  2. Retrieve the named function with getattr.
  3. Validate the function's signature matches the required pattern:
       (sources: dict[str, pd.DataFrame]) -> pd.DataFrame
  4. Cache the loaded callable so each (module, function) pair is imported
     only once per application run.

The loader intentionally validates the signature at load time, not at call
time, so misconfigured transforms fail loudly during the startup phase
rather than mid-execution.
"""

from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from typing import Any

import pandas as pd

from report_runner.transforms.base import TransformError

# Internal cache: "module.function" → validated callable
_TRANSFORM_CACHE: dict[str, Callable[[dict[str, pd.DataFrame]], pd.DataFrame]] = {}


class TransformLoader:
    """Loads, validates, and caches transform functions by module + function name."""

    def load(
        self, module_path: str, function_name: str
    ) -> Callable[[dict[str, pd.DataFrame]], pd.DataFrame]:
        """
        Return the transform callable for the given module and function.

        Uses an in-process cache keyed by "module_path.function_name" so
        each transform is imported exactly once per process lifetime.
        """
        cache_key = f"{module_path}.{function_name}"

        if cache_key in _TRANSFORM_CACHE:
            return _TRANSFORM_CACHE[cache_key]

        fn = self._import_function(module_path, function_name)
        self._validate_signature(fn, module_path, function_name)

        _TRANSFORM_CACHE[cache_key] = fn
        return fn

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _import_function(module_path: str, function_name: str) -> Any:
        """Import the module and retrieve the function object."""
        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            raise TransformError(
                f"Transform module '{module_path}' could not be imported: {exc}"
            ) from exc

        fn = getattr(module, function_name, None)
        if fn is None:
            raise TransformError(
                f"Transform function '{function_name}' not found in module '{module_path}'."
            )

        if not callable(fn):
            raise TransformError(
                f"'{function_name}' in module '{module_path}' is not callable."
            )

        return fn

    @staticmethod
    def _validate_signature(fn: Any, module_path: str, function_name: str) -> None:
        """
        Ensure the function signature is exactly:
            (sources: dict[str, pd.DataFrame]) -> pd.DataFrame

        We check:
          - Exactly one positional parameter named 'sources'
          - No *args or **kwargs
        """
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())

        # Must have exactly one parameter.
        if len(params) != 1:
            raise TransformError(
                f"Transform '{module_path}.{function_name}' must have exactly one "
                f"parameter named 'sources', but has {len(params)} parameter(s): "
                f"{[p.name for p in params]}."
            )

        param = params[0]

        # The parameter must be positional-or-keyword (not *args or **kwargs).
        if param.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.POSITIONAL_ONLY,
        ):
            raise TransformError(
                f"Transform '{module_path}.{function_name}': parameter must be "
                f"positional, not *args or **kwargs."
            )

        if param.name != "sources":
            raise TransformError(
                f"Transform '{module_path}.{function_name}': parameter must be named "
                f"'sources', got '{param.name}'."
            )
