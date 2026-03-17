"""
Tests for config/loader.py and config/models.py.

Covers:
  - Valid YAML is parsed into WorkflowConfig with correct values.
  - Invalid YAML (syntax error) raises ConfigurationError.
  - ${VAR} placeholders are interpolated from environment.
  - Missing ${VAR} raises ConfigurationError immediately.
  - Unknown report names in notifications raise ConfigurationError.
  - Unknown report names in outputs raise ConfigurationError.
  - Invalid on_failure value raises ConfigurationError.
  - Invalid deadline_time raises ConfigurationError.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from report_runner.config.loader import load_workflow
from report_runner.config.models import ConfigurationError, WorkflowConfig


# ── Fixtures ──────────────────────────────────────────────────────────────────

def write_yaml(tmp_path: Path, content: str) -> Path:
    """Write YAML content to a temp file and return its path."""
    yaml_file = tmp_path / "workflow.yaml"
    yaml_file.write_text(textwrap.dedent(content), encoding="utf-8")
    return yaml_file


MINIMAL_VALID_YAML = """\
    workflow:
      name: "Test Workflow"
      reports:
        - name: "Report A"
          on_failure: skip
          sources:
            - alias: "data"
              type: sql
              database_alias: "oracle_prod"
              sql_file: "sql/query.sql"
    """


# ── Valid config tests ────────────────────────────────────────────────────────

def test_load_minimal_valid_yaml(tmp_path: Path) -> None:
    """A minimal valid YAML is parsed correctly."""
    yaml_file = write_yaml(tmp_path, MINIMAL_VALID_YAML)
    config = load_workflow(yaml_file)

    assert isinstance(config, WorkflowConfig)
    assert config.name == "Test Workflow"
    assert len(config.reports) == 1
    assert config.reports[0].name == "Report A"
    assert config.reports[0].on_failure == "skip"


def test_load_config_with_transform(tmp_path: Path) -> None:
    """A report with a transform block is parsed correctly."""
    yaml_file = write_yaml(tmp_path, """\
        workflow:
          name: "FX Report"
          reports:
            - name: "FX Merged"
              on_failure: skip
              sources:
                - alias: "txn"
                  type: sql
                  database_alias: "oracle_prod"
                  sql_file: "sql/txn.sql"
                - alias: "rates"
                  type: api
                  url: "https://api.example.com/rates"
                  method: GET
                  response_path: "$.rates"
              transform:
                module: "transforms.examples.fx_reconciliation"
                function: "merge_with_rates"
        """)
    config = load_workflow(yaml_file)
    report = config.reports[0]
    assert report.transform is not None
    assert report.transform.module == "transforms.examples.fx_reconciliation"
    assert len(report.sources) == 2


def test_env_var_interpolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """${VAR} placeholders in YAML are replaced with environment values."""
    monkeypatch.setenv("MY_API_KEY", "secret123")
    yaml_file = write_yaml(tmp_path, """\
        workflow:
          name: "API Workflow"
          reports:
            - name: "API Report"
              on_failure: skip
              sources:
                - alias: "api_data"
                  type: api
                  url: "https://api.example.com/data"
                  method: GET
                  headers:
                    X-Api-Key: "${MY_API_KEY}"
        """)
    config = load_workflow(yaml_file)
    source = config.reports[0].sources[0]
    assert source.headers["X-Api-Key"] == "secret123"  # type: ignore[union-attr]


# ── Invalid config tests ──────────────────────────────────────────────────────

def test_missing_env_var_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ${VAR} referencing an undefined env variable raises ConfigurationError."""
    monkeypatch.delenv("UNDEFINED_VAR", raising=False)
    yaml_file = write_yaml(tmp_path, """\
        workflow:
          name: "Broken"
          reports:
            - name: "R"
              on_failure: skip
              sources:
                - alias: "src"
                  type: api
                  url: "https://api.example.com"
                  headers:
                    X-Key: "${UNDEFINED_VAR}"
        """)
    with pytest.raises(ConfigurationError, match="UNDEFINED_VAR"):
        load_workflow(yaml_file)


def test_syntax_error_in_yaml_raises(tmp_path: Path) -> None:
    """A YAML file with syntax errors raises ConfigurationError."""
    yaml_file = tmp_path / "workflow.yaml"
    yaml_file.write_text("workflow:\n  name: [unclosed", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Invalid YAML"):
        load_workflow(yaml_file)


def test_nonexistent_file_raises(tmp_path: Path) -> None:
    """Passing a non-existent file path raises ConfigurationError."""
    with pytest.raises(ConfigurationError, match="not found"):
        load_workflow(tmp_path / "missing.yaml")


def test_invalid_on_failure_raises(tmp_path: Path) -> None:
    """An invalid on_failure value raises ConfigurationError."""
    yaml_file = write_yaml(tmp_path, """\
        workflow:
          name: "Bad"
          reports:
            - name: "R"
              on_failure: halt_and_catch_fire
              sources:
                - alias: "s"
                  type: sql
                  database_alias: "oracle_prod"
                  sql_file: "sql/q.sql"
        """)
    with pytest.raises(ConfigurationError):
        load_workflow(yaml_file)


def test_invalid_deadline_time_raises(tmp_path: Path) -> None:
    """A deadline_time not in HH:MM format raises ConfigurationError."""
    yaml_file = write_yaml(tmp_path, """\
        workflow:
          name: "PC Workflow"
          reports:
            - name: "R"
              on_failure: skip
              sources:
                - alias: "s"
                  type: sql
                  database_alias: "oracle_prod"
                  sql_file: "sql/q.sql"
          preconditions:
            - type: query_poller
              description: "Check"
              database_alias: "oracle_prod"
              sql_file: "sql/check.sql"
              deadline_time: "25:99"
        """)
    with pytest.raises(ConfigurationError):
        load_workflow(yaml_file)


def test_unknown_report_in_notification_raises(tmp_path: Path) -> None:
    """A notification referencing an undefined report raises ConfigurationError."""
    yaml_file = write_yaml(tmp_path, """\
        workflow:
          name: "Cross-Ref Test"
          reports:
            - name: "Real Report"
              on_failure: skip
              sources:
                - alias: "s"
                  type: sql
                  database_alias: "oracle_prod"
                  sql_file: "sql/q.sql"
          notifications:
            - type: email
              smtp_alias: "smtp_corp"
              to: ["user@example.com"]
              subject: "Test"
              body_template: "templates/email.j2"
              reports:
                - "Real Report"
                - "Ghost Report"
        """)
    with pytest.raises(ConfigurationError, match="Ghost Report"):
        load_workflow(yaml_file)


def test_unknown_report_in_output_raises(tmp_path: Path) -> None:
    """An output workbook_group referencing an undefined report raises ConfigurationError."""
    yaml_file = write_yaml(tmp_path, """\
        workflow:
          name: "Output Test"
          reports:
            - name: "Report A"
              on_failure: skip
              sources:
                - alias: "s"
                  type: sql
                  database_alias: "oracle_prod"
                  sql_file: "sql/q.sql"
          outputs:
            - type: excel
              output_dir: "output"
              workbook_groups:
                - workbook: "file.xlsx"
                  reports:
                    - "Report A"
                    - "Report B Does Not Exist"
        """)
    with pytest.raises(ConfigurationError, match="Report B Does Not Exist"):
        load_workflow(yaml_file)
