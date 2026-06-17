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

## Setup

Your API key is generated in Reportnet under **Dataflow Settings → Generate new API key**.

```python
from reportnet import ReportnetClient

client = ReportnetClient(api_key="your-api-key")
```

### Secure key storage

Store keys in the OS keychain (macOS Keychain, Windows Credential Manager, etc.) so they never appear in source code:

```python
import reportnet

# Save once (e.g. in a setup script)
reportnet.save_key(dataflow_id=11720, api_key="your-api-key")

# Then create clients without the key in code
client = ReportnetClient.from_keyring(dataflow_id=11720)
```

### DataflowClient — reduce repetition

If you always work with the same dataflow and provider, use `for_dataflow()` to pre-fill those IDs:

```python
df = client.for_dataflow(dataflow_id=11720, provider_id=42)

# No need to repeat dataflow_id / provider_id on every call
df.import_file(dataset_id=35432, file="data.csv")
df.add_validation_job(dataset_id=35432)
df.etl_export(dataset_id=35432)
```

## Import data

```python
# From a file path
handle = client.import_file(
    dataset_id=35432,
    dataflow_id=11720,
    file="data.csv",
    replace=True,
)
handle.wait()  # blocks until done

# From a polars DataFrame (pandas also works via narwhals)
import polars as pl

df = pl.DataFrame({"country": ["IE", "DE"], "value": [1.2, 3.4]})
handle = client.import_file(dataset_id=35432, dataflow_id=11720, file=df)
handle.wait()
```

## Export data

All export methods are asynchronous and return a `JobHandle`. Call `.result()` to wait for completion and receive the file bytes.

```python
# Full dataset export — returns a ZIP of CSVs
handle = client.etl_export(dataset_id=35432, dataflow_id=11720)
zip_bytes = handle.result()

with open("export.zip", "wb") as f:
    f.write(zip_bytes)

# Single-table export (CSV or XLSX)
handle = client.export_file(dataset_id=35432, table_schema_id="abc123", mime_type="xlsx")
xlsx_bytes = handle.result()

# Whole-dataset export (all tables, async)
handle = client.export_dataset_file(dataset_id=35432, mime_type="zip")
zip_bytes = handle.result()

# BigData / datalake variants
handle = client.export_file_dl(dataset_id=35432, table_schema_id="abc123")
handle = client.export_dataset_file_dl(dataset_id=35432)
```

## Validate a dataset

```python
handle = client.add_validation_job(dataset_id=35432, dataflow_id=11720)
handle.wait()

# Retrieve grouped results
results = client.list_group_validations(dataset_id=35432, dataflow_id=11720)

# Download validation results for a release snapshot
csv_bytes = client.download_validation_snapshot(
    snapshot_id=7, dataset_id=35432, dataflow_id=11720, provider_id=42
)
```

## Job polling

All async calls return a `JobHandle`. You can poll manually or use `.wait()` / `.result()`:

```python
from reportnet import JobStatus

handle = client.import_file(...)

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

## Reporter datasets

Pass `provider_id` to any method when submitting on behalf of a reporting country.
It is also forwarded automatically to all polling requests.

```python
client.import_file(dataset_id=..., dataflow_id=..., file="data.csv", provider_id=42)
client.add_validation_job(dataset_id=..., dataflow_id=..., provider_id=42)
```

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
from reportnet import AuthError, APIError, JobFailedError, RateLimitError

try:
    handle = client.import_file(...)
    handle.wait()
except AuthError:
    print("Invalid or expired API key")
except RateLimitError:
    print("Rate limit hit — back off and retry")
except JobFailedError as e:
    print(f"Job {e.job_id} ended with {e.status}")
except APIError as e:
    print(f"HTTP {e.status_code}: {e.response_body}")
```

Transient network errors and 5xx responses on GET requests are retried automatically
(up to 3 times, exponential back-off). POST and PUT are not retried to avoid
creating duplicate jobs.

## Development

```bash
# Requires uv — https://docs.astral.sh/uv/
uv sync          # create .venv and install all dev dependencies
uv run pytest    # run tests
uv run ruff check src tests
uv run mypy src
```
