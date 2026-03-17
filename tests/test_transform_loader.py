"""
Tests for transforms/loader.py and transforms/identity.py.

Covers:
  - Valid transform function is loaded and returns a callable.
  - Loading the same function twice uses the cache (module imported once).
  - Non-existent module raises TransformError.
  - Non-existent function in a valid module raises TransformError.
  - Wrong parameter name raises TransformError.
  - Extra parameters raise TransformError.
  - IdentityTransform passes a single DataFrame through unchanged.
  - IdentityTransform raises TransformError with multiple sources.
"""

from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from report_runner.transforms.base import TransformError
from report_runner.transforms.identity import IdentityTransform
from report_runner.transforms.loader import TransformLoader, _TRANSFORM_CACHE


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_module(name: str, fn_name: str, fn_body: str) -> str:
    """
    Register a synthetic module in sys.modules with a transform function.
    Returns the module path string.
    """
    module = types.ModuleType(name)
    # Compile and exec the function definition in the module's namespace.
    exec(  # noqa: S102
        f"import pandas as pd\ndef {fn_name}(sources):\n    {fn_body}\n",
        module.__dict__,
    )
    sys.modules[name] = module
    return name


def _cleanup_cache(*keys: str) -> None:
    """Remove test entries from the global transform cache."""
    for key in keys:
        _TRANSFORM_CACHE.pop(key, None)


# ── Load tests ────────────────────────────────────────────────────────────────

def test_load_valid_transform() -> None:
    """A valid transform function is loaded and is callable."""
    mod = _make_module("test_valid_mod", "my_transform", "return pd.DataFrame()")
    _cleanup_cache(f"{mod}.my_transform")

    loader = TransformLoader()
    fn = loader.load(mod, "my_transform")

    assert callable(fn)
    result = fn({"x": pd.DataFrame()})
    assert isinstance(result, pd.DataFrame)

    _cleanup_cache(f"{mod}.my_transform")


def test_cache_prevents_double_import() -> None:
    """The same (module, function) pair is returned from cache on second call."""
    mod = _make_module("test_cache_mod", "cached_fn", "return pd.DataFrame()")
    cache_key = f"{mod}.cached_fn"
    _cleanup_cache(cache_key)

    loader = TransformLoader()
    fn1 = loader.load(mod, "cached_fn")
    fn2 = loader.load(mod, "cached_fn")

    assert fn1 is fn2  # Same object from cache.
    _cleanup_cache(cache_key)


def test_nonexistent_module_raises() -> None:
    """Referencing a module that cannot be imported raises TransformError."""
    loader = TransformLoader()
    with pytest.raises(TransformError, match="could not be imported"):
        loader.load("nonexistent.module.path", "some_fn")


def test_nonexistent_function_in_module_raises() -> None:
    """Referencing a function that doesn't exist in the module raises TransformError."""
    mod = _make_module("test_missing_fn_mod", "real_fn", "return pd.DataFrame()")
    _cleanup_cache(f"{mod}.missing_fn")

    loader = TransformLoader()
    with pytest.raises(TransformError, match="not found"):
        loader.load(mod, "missing_fn")


def test_wrong_parameter_name_raises() -> None:
    """A function with parameter named anything other than 'sources' raises TransformError."""
    mod = _make_module("test_wrong_param", "bad_fn", "return pd.DataFrame()")
    # Override with correct structure but wrong param name.
    module = sys.modules[mod]
    exec(  # noqa: S102
        "import pandas as pd\ndef bad_fn(data):\n    return pd.DataFrame()\n",
        module.__dict__,
    )
    _cleanup_cache(f"{mod}.bad_fn")

    loader = TransformLoader()
    with pytest.raises(TransformError, match="'sources'"):
        loader.load(mod, "bad_fn")


def test_too_many_parameters_raises() -> None:
    """A function with more than one parameter raises TransformError."""
    mod = _make_module("test_too_many", "multi_param", "return pd.DataFrame()")
    module = sys.modules[mod]
    exec(  # noqa: S102
        "import pandas as pd\ndef multi_param(sources, extra):\n    return pd.DataFrame()\n",
        module.__dict__,
    )
    _cleanup_cache(f"{mod}.multi_param")

    loader = TransformLoader()
    with pytest.raises(TransformError, match="exactly one"):
        loader.load(mod, "multi_param")


# ── IdentityTransform tests ───────────────────────────────────────────────────

def test_identity_transform_passes_single_df_through() -> None:
    """IdentityTransform returns the sole input DataFrame unchanged."""
    df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    transform = IdentityTransform()
    result = transform.apply({"my_alias": df})

    pd.testing.assert_frame_equal(result, df)


def test_identity_transform_raises_on_multiple_sources() -> None:
    """IdentityTransform raises TransformError when given more than one source."""
    sources = {
        "source_a": pd.DataFrame({"x": [1]}),
        "source_b": pd.DataFrame({"y": [2]}),
    }
    transform = IdentityTransform()
    with pytest.raises(TransformError, match="exactly 1 source"):
        transform.apply(sources)


def test_identity_transform_raises_on_zero_sources() -> None:
    """IdentityTransform raises TransformError when given an empty dict."""
    transform = IdentityTransform()
    with pytest.raises(TransformError):
        transform.apply({})
