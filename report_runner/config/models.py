"""
Pydantic v2 models that define the complete schema for a workflow YAML file.

Every field maps 1-to-1 with a YAML key, making the data contract between
the YAML author and the runtime code explicit and self-documenting.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Custom exception ──────────────────────────────────────────────────────────

class ConfigurationError(Exception):
    """Raised when the YAML workflow config is invalid or incomplete."""


# ── Precondition models ───────────────────────────────────────────────────────

class PreconditionConfig(BaseModel):
    type: Literal["query_poller"]
    description: str
    database_alias: str
    sql_file: str
    poll_interval_minutes: int = Field(default=5, ge=1)
    deadline_time: str  # HH:MM 24-hour local time

    @field_validator("deadline_time")
    @classmethod
    def validate_deadline_time(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) != 2:
            raise ConfigurationError(
                f"deadline_time '{v}' must be in HH:MM format (e.g. '08:00')."
            )
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError:
            raise ConfigurationError(
                f"deadline_time '{v}' contains non-integer parts."
            )
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ConfigurationError(
                f"deadline_time '{v}' is out of range (hour 0-23, minute 0-59)."
            )
        return v


# ── Source models ─────────────────────────────────────────────────────────────

class SqlSourceConfig(BaseModel):
    alias: str
    type: Literal["sql"]
    database_alias: str
    sql_file: str


class ApiSourceConfig(BaseModel):
    alias: str
    type: Literal["api"]
    url: str
    method: Literal["GET", "POST"] = "GET"
    timeout_seconds: int = Field(default=30, ge=1)
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | None = None  # POST body, optional
    response_path: str | None = None    # JSONPath to extract target array


# A source is either SQL or API — Pydantic discriminates on the `type` field.
SourceConfig = SqlSourceConfig | ApiSourceConfig


# ── Transform model ───────────────────────────────────────────────────────────

class TransformConfig(BaseModel):
    module: str    # e.g. "transforms.examples.fx_reconciliation"
    function: str  # e.g. "merge_with_rates"


# ── Report model ──────────────────────────────────────────────────────────────

class ReportConfig(BaseModel):
    name: str
    on_failure: Literal["skip", "abort"] = "skip"
    sources: list[SourceConfig] = Field(min_length=1)
    transform: TransformConfig | None = None

    @field_validator("sources", mode="before")
    @classmethod
    def parse_sources(cls, raw: list) -> list[SourceConfig]:
        """Deserialise each source dict into the correct typed model.

        Accepts both plain dicts (from YAML) and already-typed model instances
        (from programmatic construction in tests or code).
        """
        parsed: list[SourceConfig] = []
        for item in raw:
            # If already a typed model, pass it through unchanged.
            if isinstance(item, (SqlSourceConfig, ApiSourceConfig)):
                parsed.append(item)
                continue
            if not isinstance(item, dict):
                raise ConfigurationError(
                    f"Source config must be a dict or a typed model, got {type(item).__name__}."
                )
            source_type = item.get("type")
            if source_type == "sql":
                parsed.append(SqlSourceConfig(**item))
            elif source_type == "api":
                parsed.append(ApiSourceConfig(**item))
            else:
                raise ConfigurationError(
                    f"Unknown source type '{source_type}'. Must be 'sql' or 'api'."
                )
        return parsed


# ── Output / export models ────────────────────────────────────────────────────

class WorkbookGroup(BaseModel):
    """Maps a set of report names to a single output .xlsx file."""
    workbook: str           # filename template, may contain {date}
    reports: list[str]      # report names to include as sheets


class ExcelOutputConfig(BaseModel):
    type: Literal["excel"]
    output_dir: str
    workbook_groups: list[WorkbookGroup] = Field(default_factory=list)


# Currently only Excel is supported; union keeps the door open for future formats.
OutputConfig = ExcelOutputConfig


# ── Notification models ───────────────────────────────────────────────────────

class EmailNotificationConfig(BaseModel):
    type: Literal["email"]
    smtp_alias: str
    to: list[str] = Field(min_length=1)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    subject: str
    body_template: str  # path to .j2 template file
    reports: list[str]  # which report names to include in this notification


NotificationConfig = EmailNotificationConfig


# ── Top-level workflow model ──────────────────────────────────────────────────

class WorkflowConfig(BaseModel):
    name: str
    description: str = ""
    preconditions: list[PreconditionConfig] = Field(default_factory=list)
    reports: list[ReportConfig] = Field(min_length=1)
    outputs: list[OutputConfig] = Field(default_factory=list)
    notifications: list[NotificationConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_cross_references(self) -> WorkflowConfig:
        """
        Ensure every name referenced in outputs and notifications actually
        exists in the reports list.  Catch typos at load time, not at runtime.
        """
        defined_names = {r.name for r in self.reports}

        for output in self.outputs:
            if isinstance(output, ExcelOutputConfig):
                for group in output.workbook_groups:
                    for name in group.reports:
                        if name not in defined_names:
                            raise ConfigurationError(
                                f"Output workbook_group references unknown report "
                                f"'{name}'. Defined reports: {sorted(defined_names)}"
                            )

        for notification in self.notifications:
            for name in notification.reports:
                if name not in defined_names:
                    raise ConfigurationError(
                        f"Notification block references unknown report '{name}'. "
                        f"Defined reports: {sorted(defined_names)}"
                    )

        return self


class RootConfig(BaseModel):
    """The top-level wrapper matching the 'workflow:' key in YAML."""
    workflow: WorkflowConfig
