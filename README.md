# reportnet-client

Python client for the [EEA Reportnet 3 REST API](https://help.reportnet.europa.eu/rest-api/).

## Installation

```bash
pip install reportnet

# Optional: DataFrame support (polars, pandas, modin — via narwhals)
pip install "reportnet[dataframe]"

# Optional: system keychain storage for API keys
pip install "reportnet[keyring]"
```

## Concepts

Reportnet 3 organises data in a three-level hierarchy:

```
Dataflow  (a reporting obligation, e.g. "EU GHG Inventory")
  └── Reporter / DataProvider  (a country or organisation)
        └── Dataset  (the data store for that reporter)
              └── Table / Field  (schema and rows)
  └── Reference Dataset  (shared lookup data, no reporter)
```

- A **Dataflow** describes what data is expected and from whom.
- Each **Reporter** (country or organisation) has one reporting **Dataset** per dataflow.
- **Reference Datasets** hold shared codelist/lookup values; they are not tied to a specific reporter.

## Setup

Your API key is generated in Reportnet under **Dataflow Settings → Generate new API key**.
One key typically covers a single dataflow.

```python
from reportnet import ReportnetClient

client = ReportnetClient(api_key="your-api-key")
```

### Secure key storage

Store keys in the OS keychain (macOS Keychain, Windows Credential Manager, etc.)
so they never appear in source code:

```python
import reportnet

# Save once (e.g. in a setup script)
reportnet.save_key(dataflow_id=1619, api_key="your-api-key")

# Load at runtime — no key in code
client = ReportnetClient.from_keyring(dataflow_id=1619)
```

## Working with a dataflow

`for_dataflow()` returns a `DataflowClient` that pre-fills the dataflow ID on every call.
Use `for_provider()` within it to further scope to a specific reporter.

```python
# Custodian / admin — no reporter scope
df = client.for_dataflow(1619)

info = df.get_dataflow()       # DataflowInfo(id=1619, name=..., type="REPORTING", status="PUBLIC")
reporters = df.get_reporters() # [Reporter(provider_id=42, dataset_id=93953, ...), ...]
df.is_big_dataflow()           # True / False (BigData vs Citus backend)

# Scope to a specific reporter country (provider_id from the reporters list)
ie = df.for_provider(42)

# All import/export/validation calls below now use provider_id=42 automatically
ie.import_file(dataset_id=93953, file="ireland.csv")
ie.add_validation_job(dataset_id=93953)
frames = ie.etl_export(dataset_id=93953).to_frames()
```

## Import data

```python
# From a file path
handle = ie.import_file(
    dataset_id=93953,
    file="data.csv",
    replace=False,          # append (True = replace all existing rows)
    table_schema_id="...",  # optional: target a specific table
)
handle.wait()  # blocks until the import job finishes

# From a polars DataFrame (pandas also works via narwhals)
import polars as pl
df_data = pl.DataFrame({"category": ["A"], "cyear": [2024], "gas": ["CO2"]})
handle = ie.import_file(dataset_id=93953, file=df_data)
handle.wait()

# Or call directly on the client (dataflow_id and provider_id explicit)
client.import_file(
    dataset_id=93953,
    dataflow_id=1619,
    provider_id=42,
    file="data.csv",
)
```

The default delimiter is `|` (pipe), which is what the Reportnet API expects.
Do **not** include a `record_id` column — Reportnet assigns that on ingestion.

## Export data

All export methods return a `JobHandle`. Call `.result()` for raw bytes or `.to_frames()`
to get a `dict` of DataFrames (requires `reportnet[dataframe]`).

```python
# Full dataset export — ZIP of CSVs, one file per table
handle = ie.etl_export(dataset_id=93953)
zip_bytes = handle.result(poll_interval=10.0, timeout=600.0)

# Export directly into DataFrames
frames = ie.etl_export(dataset_id=93953).to_frames()
# {"Table1a": <polars.DataFrame>, "Table1b": <polars.DataFrame>, ...}
for name, frame in frames.items():
    print(name, frame.shape)

# Single-table export (CSV or XLSX)
handle = ie.export_file(dataset_id=93953, table_schema_id="abc123", mime_type="xlsx")
xlsx_bytes = handle.result()

# Whole-dataset export (BigData variant)
handle = ie.export_dataset_file_dl(dataset_id=93953)
zip_bytes = handle.result()
```

## Dataset schema

Retrieve table names, field names, types and required flags for any dataset:

```python
schema = df.get_schema(dataset_id=93953)

for table in schema.tables:
    print(table.name)
    print("  required:", table.required_columns())
    print("  all:     ", table.column_names())

# Look up a specific table and inspect fields
table = schema.table("Table1a")
for field in table.fields:
    print(field.name, field.type, "required" if field.required else "")
# category  FieldType.LINK           required
# cyear     FieldType.NUMBER_INTEGER  required
# cvalue    FieldType.NUMBER_DECIMAL
```

`field.type` is a `FieldType` enum: `TEXT`, `NUMBER_INTEGER`, `NUMBER_DECIMAL`, `DATE`,
`LINK`, `CODELIST`, `MULTISELECT_CODELIST`, …

## Validate a dataset

```python
# Trigger validation and wait for it to finish
handle = ie.add_validation_job(dataset_id=93953)
handle.wait(poll_interval=10.0, timeout=600.0)

# Read grouped validation results (BigData variant)
results = ie.list_group_validations_dl(dataset_id=93953)

# Download validation results for a release snapshot (CSV bytes)
csv_bytes = ie.download_validation_snapshot(snapshot_id=7, dataset_id=93953)
```

## Release history

```python
releases = ie.list_historic_releases(dataset_id=93953)
for r in releases:
    print(r["releaseDate"], r.get("status"))
```

## Dataset management

```python
# Check whether an import is currently running
status = df.check_import_process(dataset_id=93953)
# {"anyLockAssigned": True, "importInProgress": True}

# Delete all data before a full re-import
ie.delete_dataset_data(dataset_id=93953)

# Delete a single table's data
ie.delete_table_data(dataset_id=93953, table_schema_id="68dd41f0...")
```

## Reference datasets

Reference datasets hold shared codelist or lookup data for a dataflow.
They have no reporter (`provider_id`) and can be locked to prevent edits
during active reporting periods.

```python
REF_DS_ID = 12345

# Import new reference data (custodian only)
df.import_file(dataset_id=REF_DS_ID, file="codelists.csv", replace=True)

# Lock the reference dataset (prevent further edits)
df.set_reference_dataset_updatable(dataset_id=REF_DS_ID, updatable=False)

# Unlock it again
df.set_reference_dataset_updatable(dataset_id=REF_DS_ID, updatable=True)
```

## Job polling

All async calls return a `JobHandle`. You can poll manually or use `.wait()` / `.result()`:

```python
from reportnet import JobStatus

handle = ie.import_file(dataset_id=93953, file="data.csv")

# Check once without blocking
status = handle.status()  # JobStatus.IN_PROGRESS

# Block with a timeout and a progress callback
handle.wait(
    poll_interval=5.0,
    timeout=300.0,
    on_status=lambda s: print(f"status: {s}"),
)
```

Terminal statuses: `FINISHED`, `FAILED`, `REFUSED`, `CANCELED`, `CANCELED_BY_ADMIN`.
`.wait()` raises `JobFailedError` for any terminal status other than `FINISHED`.

## Provider helpers

Look up data provider IDs by country code or group membership:

```python
from reportnet import by_id, by_country, by_group

by_id(42)              # DataProvider(provider_id=42, country_code='AD', ...)
by_country("IE")       # [DataProvider(...), ...]  — may be more than one
by_group("EEA")        # all EEA member providers
by_group("EU", field="eurostat_group")  # EU providers by Eurostat classification
```

## Error handling

```python
from reportnet import AuthError, APIError, DatasetLockedError, JobFailedError, RateLimitError

try:
    handle = ie.import_file(dataset_id=93953, file="data.csv")
    handle.wait()
except AuthError:
    print("Invalid or expired API key")
except RateLimitError:
    print("Rate limit hit — back off and retry")
except DatasetLockedError:
    print("Another job is already running on this dataset — try again shortly")
except JobFailedError as e:
    print(f"Job {e.job_id} ended with {e.status}")
except APIError as e:
    print(f"HTTP {e.status_code}: {e.response_body}")
```

Transient network errors and 5xx responses on GET requests are retried automatically
(up to 3 times, exponential back-off). POST and PUT are not retried to avoid
duplicate jobs.

## Development

```bash
# Requires uv — https://docs.astral.sh/uv/
uv sync                       # create .venv and install all dev dependencies
uv run pytest                 # run unit tests (integration tests skipped)
uv run pytest --integration   # also run live API tests (requires keyring credentials)
uv run ruff check src tests
uv run mypy src
```
