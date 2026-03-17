# Report Runner

A production-grade, modular report automation CLI for Windows Task Scheduler.
Fetches data from SQL databases and REST APIs, exports to `.xlsx`, and emails
results — with execution and distribution fully decoupled.

---

## Project Structure

```
report_runner/          Core application package
├── config/             YAML schema models + loader
├── database/           DB connector abstraction (Oracle, MSSQL, PostgreSQL)
├── sources/            DataSource abstraction (SQL, API)
├── transforms/         TransformStep abstraction + loader + examples
├── reports/            CompositeReportRunner
├── exporters/          ExcelExporter (openpyxl)
├── notifications/      EmailNotifier (smtplib + Jinja2)
├── preconditions/      QueryPollerPreconditionChecker
├── orchestrator/       WorkflowRunner (phases coordinator)
├── logging_setup/      Loguru configuration
├── container.py        Dependency injection wiring
└── models.py           Runtime data models (ReportResult, ExportedFile, etc.)
main.py                 CLI entrypoint (zero business logic)
transforms/             User-defined transform functions (importlib-loaded)
examples/               Sample YAML workflow + SQL stubs
templates/              Jinja2 email templates
tests/                  pytest test suite
```

---

## Setup

### 1. Install Python 3.11+

```bash
python --version  # Must be 3.11 or newer
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -e ".[dev]"
```

### 4. Configure credentials

```bash
cp .env.example .env
# Edit .env and fill in all database, SMTP, and API key values.
```

The `.env` file is loaded automatically at startup via `python-dotenv`.
**Never commit `.env` to version control.**

---

## Running the CLI

```bash
# Run a workflow
python main.py --workflow examples/daily_reconciliation.yaml

# Validate YAML without making any database or API calls
python main.py --workflow examples/daily_reconciliation.yaml --dry-run

# Override log level for this run
python main.py --workflow examples/daily_reconciliation.yaml --log-level DEBUG
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0`  | All reports succeeded, all emails sent |
| `1`  | Precondition deadline exceeded — workflow aborted |
| `2`  | One or more reports failed (partial success), emails still sent |
| `3`  | Unrecoverable error (invalid YAML, missing `.env` key, bad transform) |

---

## Windows Task Scheduler Setup

1. Open **Task Scheduler** → **Create Basic Task**
2. Set the trigger (e.g., Daily at 06:00)
3. Action: **Start a program**
   - Program: `C:\path\to\.venv\Scripts\python.exe`
   - Arguments: `C:\path\to\main.py --workflow C:\path\to\workflow.yaml`
   - Start in: `C:\path\to\project_root`
4. Under **Settings**, check "Run task as soon as possible after a scheduled start is missed"

> The application has no internal scheduler — it runs once and exits.
> Task Scheduler handles recurrence entirely.

---

## How to Add a New Data Source Type

1. Create `report_runner/sources/my_source.py`:
   ```python
   from report_runner.sources.base import DataSource
   class MyDataSource(DataSource):
       def fetch(self) -> pd.DataFrame: ...
   ```

2. Add a config model in `report_runner/config/models.py`:
   ```python
   class MySourceConfig(BaseModel):
       alias: str
       type: Literal["my_type"]
       ...
   ```

3. Update the `SourceConfig` union type in `config/models.py`.

4. Add a branch in `ReportConfig.parse_sources` validator.

5. Add a branch in `sources/factory.py`:
   ```python
   if isinstance(config, MySourceConfig):
       return MyDataSource(config)
   ```

No other files need to change.

---

## How to Write a Transform Function

Transform functions live in the `transforms/` directory (or any importable module).

**Required signature — no deviations accepted:**
```python
def my_transform(sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
    ...
```

**Example:**
```python
# transforms/examples/fx_reconciliation.py
import pandas as pd

def merge_with_rates(sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
    transactions = sources["transactions"]
    fx_rates = sources["fx_rates"]
    merged = transactions.merge(fx_rates, on="currency_code", how="left")
    merged["amount_mdl"] = merged["amount"] * merged["rate"]
    return merged[["transaction_id", "amount", "currency_code", "rate", "amount_mdl"]]
```

**Reference in YAML:**
```yaml
transform:
  module: "transforms.examples.fx_reconciliation"
  function: "merge_with_rates"
```

**Rules for transform functions:**
- Must be **pure**: no side effects, no I/O, no global state mutations.
- The `sources` keys must match the `alias` values of the report's sources.
- The loader validates the signature at load time and raises `TransformError`
  if the signature is wrong.
- Functions are cached after the first load — safe to reference multiple times.

---

## How to Configure Independent Distribution to Multiple Recipients

Execution (running reports → `.xlsx`) and distribution (sending emails) are
**completely decoupled phases**. Each `notifications` block independently selects
its recipients and its subset of reports.

**Example:** Reports A, B, C go to `team@company.com`. Reports B and C also go
independently to `partner@external.com`.

```yaml
notifications:
  # Block 1: full team receives everything
  - type: email
    smtp_alias: "smtp_corp"
    to: ["team@company.com"]
    subject: "Daily Report — {date}"
    body_template: "templates/email_body.html.j2"
    reports:
      - "Report A"
      - "Report B"
      - "Report C"

  # Block 2: partner receives a subset, independently
  - type: email
    smtp_alias: "smtp_corp"
    to: ["partner@external.com"]
    subject: "Partner Report — {date}"
    body_template: "templates/email_body.html.j2"
    reports:
      - "Report B"
      - "Report C"
```

**This requires zero code changes** — only YAML edits.

Each notification block:
- Filters `ReportResult` objects to only its listed reports.
- Attaches only `.xlsx` files that contain at least one of its reports.
- Sends independently — a failure in one block does not prevent others.

---

## Running Tests

```bash
pytest
# With verbose output:
pytest -v
# With coverage:
pip install pytest-cov
pytest --cov=report_runner --cov-report=term-missing
```

---

## Adding a New Database Type

1. Create `report_runner/database/my_db.py` implementing `DatabaseConnector`.
2. Add a branch in `database/factory.py`:
   ```python
   if alias_lower.startswith("mydb"):
       from report_runner.database.my_db import MyDbConnector
       return MyDbConnector(alias)
   ```
3. Add the corresponding `.env` keys (following the `DB_{ALIAS_UPPER}_*` convention).
4. Document the new keys in `.env.example`.

---

## Architecture Notes

- **No SQLAlchemy** — raw driver connections only.
- **No parallel execution** — all reports, sources, and notifications are serial.
- **No inline SQL** — all queries live in `.sql` files referenced by YAML.
- **No credentials in YAML** — only `${VAR_NAME}` references resolved from `.env`.
- **No business logic in `main.py`** — only DI wiring and argument parsing.
