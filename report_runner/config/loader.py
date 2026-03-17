"""
YAML workflow loader.

Responsibilities:
1. Read the .yaml file from disk.
2. Interpolate ${VAR_NAME} placeholders with values from the loaded .env.
3. Parse and validate the resulting dict into WorkflowConfig via Pydantic.

Raises ConfigurationError (not a generic exception) for every identifiable
misconfiguration so callers get a clear, actionable message.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from report_runner.config.models import ConfigurationError, RootConfig, WorkflowConfig

# Matches ${SOME_VAR_NAME} — the only interpolation syntax we support.
_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def load_workflow(yaml_path: str | Path) -> WorkflowConfig:
    """
    Parse a workflow YAML file and return a validated WorkflowConfig.

    Steps:
      1. Load .env into the process environment (adjacent to YAML, or CWD).
      2. Read the YAML file.
      3. Walk the parsed dict and replace every ${VAR} with the env value.
      4. Validate with Pydantic.
    """
    yaml_path = Path(yaml_path).resolve()
    if not yaml_path.exists():
        raise ConfigurationError(f"Workflow file not found: {yaml_path}")

    # Load .env from the project root (CWD) so credentials are available.
    load_dotenv(override=False)

    raw_text = yaml_path.read_text(encoding="utf-8")
    try:
        raw_dict = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in '{yaml_path}': {exc}") from exc

    if not isinstance(raw_dict, dict):
        raise ConfigurationError(
            f"Workflow file '{yaml_path}' must contain a YAML mapping at the top level."
        )

    interpolated = _interpolate_env_vars(raw_dict)

    try:
        root = RootConfig.model_validate(interpolated)
    except Exception as exc:
        # Re-wrap Pydantic validation errors in our own exception type so
        # callers only need to handle ConfigurationError.
        raise ConfigurationError(
            f"Workflow config validation failed:\n{exc}"
        ) from exc

    return root.workflow


def _interpolate_env_vars(obj: Any) -> Any:
    """
    Recursively walk a parsed YAML structure (dicts, lists, strings) and
    replace every ${VAR_NAME} occurrence with the matching environment variable.

    Raises ConfigurationError if any referenced variable is not set.
    """
    if isinstance(obj, dict):
        return {k: _interpolate_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate_env_vars(item) for item in obj]
    if isinstance(obj, str):
        return _replace_placeholders(obj)
    # int, float, bool, None — pass through unchanged.
    return obj


def _replace_placeholders(text: str) -> str:
    """Replace all ${VAR} occurrences in a single string."""

    def _resolve(match: re.Match) -> str:
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            raise ConfigurationError(
                f"Environment variable '{var_name}' is referenced in the workflow YAML "
                f"but is not defined in the environment or .env file."
            )
        return value

    return _ENV_VAR_PATTERN.sub(_resolve, text)
