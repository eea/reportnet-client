# reportnet-client

Python client for the [EEA Reportnet 3 REST API](https://help.reportnet.europa.eu/rest-api/).

## Installation

```bash
pip install -e .

# Optional: DataFrame support (polars + narwhals)
pip install -e ".[dataframe]"
```

## Setup

```python
from reportnet import ReportnetClient

client = ReportnetClient(api_key="your-api-key")
```

Your API key is generated in Reportnet under **Dataflow Settings → Generate new API key**.

## Import data

```python
# From a CSV file
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

```python
# Async export — returns a ZIP of CSVs
handle = client.etl_export(dataset_id=35432, dataflow_id=11720)
zip_bytes = handle.result()  # waits for completion, then returns the ZIP

with open("export.zip", "wb") as f:
    f.write(zip_bytes)
```

## Validate a dataset

```python
handle = client.add_validation_job(dataset_id=35432, dataflow_id=11720)
handle.wait()

# Retrieve the results
results = client.list_group_validations(dataset_id=35432, dataflow_id=11720)
```

## Job polling

All import, export, and validation calls return a `JobHandle`. You can poll manually or just call `.wait()`:

```python
from reportnet import JobStatus

handle = client.import_file(...)

# Check once without blocking
status = handle.status()
print(status)  # JobStatus.IN_PROGRESS

# Block with a timeout
handle.wait(poll_interval=5.0, timeout=300.0)
```

Terminal statuses: `FINISHED`, `FAILED`, `REFUSED`, `CANCELED`, `CANCELED_BY_ADMIN`.
`.wait()` raises `JobFailedError` for any terminal status other than `FINISHED`.

## Reporter datasets

Pass `provider_id` to any method when submitting on behalf of a reporting country:

```python
client.import_file(dataset_id=..., dataflow_id=..., file="data.csv", provider_id=42)
client.add_validation_job(dataset_id=..., dataflow_id=..., provider_id=42)
```

## Error handling

```python
from reportnet import AuthError, APIError, JobFailedError

try:
    handle = client.import_file(...)
    handle.wait()
except AuthError:
    print("Invalid API key")
except JobFailedError as e:
    print(f"Job {e.job_id} ended with {e.status}")
except APIError as e:
    print(f"HTTP {e.status_code}: {e.response_body}")
```
