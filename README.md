# reportnet-client

[![Tests](https://github.com/eea/reportnet-client/actions/workflows/tests.yml/badge.svg)](https://github.com/eea/reportnet-client/actions/workflows/tests.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
[![Licence: EUPL-1.2](https://img.shields.io/badge/licence-EUPL--1.2-blue)](LICENSE)

Python client for [EEA Reportnet 3](https://reportnet.europa.eu). Uploads,
validates and downloads reporting data through the Reportnet REST API.

Status: beta. The public API may change before 1.0.

**[Documentation](https://eea.github.io/reportnet-client/)**

## Scope

The library covers the reporting cycle up to submission:

```
connect -> read schema -> prepare data -> upload -> verify -> validate -> release
|________________________ library ______________________________|      |__ web UI __|
```

Release is not available through the API. It must be performed in the web
interface.

Two key roles exist. Reporters submit data for one country or organisation.
Custodians administer a dataflow. Permissions differ between them and affect
which operations succeed; see [Permissions](#permissions). This document is
written for reporters. Custodian operations are listed in
[Custodian operations](#custodian-operations).

## Contents

- [Installation](#installation)
- [Authentication](#authentication)
- [Complete example](#complete-example)
- [1. Connect](#1-connect)
- [2. Dataset identifiers](#2-dataset-identifiers)
- [3. Schema](#3-schema)
- [4. Data preparation](#4-data-preparation)
- [5. Upload](#5-upload)
- [6. Verify the upload](#6-verify-the-upload)
- [7. Validation](#7-validation)
- [8. Release](#8-release)
- [Download](#download)
- [Permissions](#permissions)
- [Errors](#errors)
- [Logging](#logging)
- [Custodian operations](#custodian-operations)
- [Development](#development)
- [Changelog](#changelog)
- [Licence](#licence)

## Installation

```bash
pip install "reportnet-client[dataframe,keyring] @ git+https://github.com/eea/reportnet-client.git"
```

Extras:

| Extra | Provides |
|---|---|
| `dataframe` | polars/pandas support via narwhals. Required for table handling. |
| `keyring` | API key storage in the operating system keychain. |
| `spatial` | geopandas support for geometry columns. |

## Authentication

API keys are generated in Reportnet under **Dataflow Settings → Generate new
API key**. One key applies to one dataflow.

Store the key in the system keychain:

```python
import reportnet

reportnet.save_key(dataflow_id=1234, api_key="...")
```

Load it at runtime:

```python
client = reportnet.ReportnetClient.from_keyring(dataflow_id=1234)
```

A separate sandbox environment exists for testing. It requires its own key and
VPN access. Pass `sandbox=True` to `save_key()` and `from_keyring()`.

## Complete example

```python
import polars as pl
import reportnet

DATAFLOW_ID = 1234
DATASET_ID = 56789
COUNTRY = "IT"

client = reportnet.ReportnetClient.from_keyring(dataflow_id=DATAFLOW_ID)
me = client.for_dataflow(DATAFLOW_ID).find_reporter(COUNTRY)

schema = me.get_schema(dataset_id=DATASET_ID)
table = schema.table("Contacts")

data = pl.read_excel("my_data.xlsx", sheet_name="Contacts")
data = table.cast_frame(data)

me.import_file(dataset_id=DATASET_ID, file=data, table_schema_id=table.id).wait()
print(me.verify_import(dataset_id=DATASET_ID)["Contacts"])

result = me.validate(dataset_id=DATASET_ID)
print(result.summary())
```

## 1. Connect

Scope the client to a dataflow, then to a reporter by ISO country code:

```python
client = reportnet.ReportnetClient.from_keyring(dataflow_id=DATAFLOW_ID)
flow = client.for_dataflow(DATAFLOW_ID)

me = flow.find_reporter("IT")
```

`find_reporter()` resolves the country code to the internal provider
identifier. If the code is not registered for the dataflow, it raises
`ValueError` listing the codes that are. To list them directly:

```python
for r in flow.get_reporters():
    print(r.country_code, r.country_name)
```

## 2. Dataset identifiers

A dataflow defines more than one dataset per reporter. List them by table name:

```python
me.datasets_by_table()
# {'Descriptive data': ReportingDataset(id=108953, status='PENDING'),
#  'Spatial data':     ReportingDataset(id=108958, status='PENDING')}

ds = me.dataset("Descriptive data")
ds.id
```

Reporter keys see only their own datasets. The client must be provider-scoped
for this, which `find_reporter()` does. An unscoped client raises
`DiscoveryNotPermittedError` naming the two ways to scope it.

Identifiers also appear in the dataset URL in the web interface, if they are
more convenient to copy:

```
https://reportnet.europa.eu/dataflow/1234/dataset/56789
                                                  ^^^^^ dataset identifier
```

## 3. Schema

```python
schema = me.get_schema(dataset_id=DATASET_ID)

for table in schema.tables:
    print(table.name, table.required_columns())
```

`get_template()` returns one empty typed DataFrame per table:

```python
templates = me.get_template(dataset_id=DATASET_ID)
```

Numeric, date and boolean columns are typed from the schema. Columns
constrained to a code list are typed as enumerations only when the code list
can be read, which requires administrator permissions. Otherwise they are
typed as strings and a warning is issued. `strict=True` raises
`CodelistResolutionError` instead:

```python
templates = me.get_template(dataset_id=DATASET_ID, strict=True)
```

## 4. Data preparation

```python
import polars as pl

data = pl.read_excel("my_data.xlsx", sheet_name="Contacts")
```

`cast_frame()` converts columns to the schema types and raises `ValueError` if
a value cannot be converted or a required column is missing:

```python
data = schema.table("Contacts").cast_frame(data)
```

`validate_frame()` returns the same problems as a list instead of raising:

```python
for problem in schema.table("Contacts").validate_frame(data):
    print(problem)
```

Do not include a `record_id` column. Reportnet assigns it during ingestion.

## 5. Upload

```python
table = schema.table("Contacts")

job = me.import_file(dataset_id=DATASET_ID, file=data, table_schema_id=table.id)
job.wait()
```

Uploads are asynchronous. `wait()` polls until the job reaches a terminal
state and raises `JobFailedError` if that state is not `FINISHED`.

`file` accepts a path, bytes, a file object, a DataFrame, a DuckDB relation or
a GeoDataFrame. The default column separator is `|`; pass `delimiter=","` for
comma-separated input. `replace=True` clears existing rows before loading.

Multiple tables:

```python
me.import_frames(dataset_id=DATASET_ID, frames={"Contacts": df1, "Sites": df2})
```

## 6. Verify the upload

A `FINISHED` job does not confirm that rows were stored. Reportnet accepts,
processes and reports success for input it then discards, for example when
required values are absent.

```python
me.verify_import(dataset_id=DATASET_ID)["Contacts"]
# {'records': 42, 'last_import': datetime(...), 'file_extension': 'csv'}
```

`records` is the number of rows recorded by the last import for that table, or
`None` if the table has never been imported into.

## 7. Validation

```python
result = me.validate(dataset_id=DATASET_ID)

print(result.summary())
# "dataset 56789: 3 issue(s) — 1 BLOCKER, 2 ERROR"
```

| Attribute | Meaning |
|---|---|
| `result.ok` | No `BLOCKER` or `ERROR` issues |
| `result.has_blockers` | At least one `BLOCKER` |
| `result.to_frame()` | All issues as a DataFrame |
| `result.raw` | Unmodified API response |

Validation runs asynchronously and may take several minutes. Concurrent jobs
on the same dataset raise `DatasetLockedError`.

## 8. Release

Reportnet provides no API endpoint that releases or submits a dataset. Release
must be performed in the web interface after validation completes.

## Download

Reporters can export their own reporting dataset:

```python
tables = me.etl_export(dataset_id=DATASET_ID).to_frames()
tables["Contacts"]
```

Exports are asynchronous and can take several minutes. Shared reference
datasets cannot be exported by reporter keys.

Geometry columns convert to a GeoDataFrame with the `spatial` extra:

```python
gdf = reportnet.to_geodataframe(tables["ProtectedArea"], "geometry_polygon")
```

`import_file()` accepts a GeoDataFrame directly.

## Permissions

Reportnet assigns permissions per key role. The library determines the role by
probing and adjusts request parameters accordingly:

```python
print(flow.capabilities().summary())
# "dataflow 1234: reporter key; reads must be provider-scoped"
```

| Operation | Reporter | Custodian |
|---|---|---|
| Read schema | yes | yes |
| Upload data | yes | yes |
| Verify an upload | yes | yes |
| Validate, read results | yes | yes |
| Resolve country code | yes | yes |
| Export own reporting dataset | yes | yes |
| List own dataset identifiers | yes | yes |
| List all reporters' datasets | no | yes |
| Export reference datasets | no | yes |
| Resolve code lists | no | yes |
| Read release history | no | yes |

Measured on a BigData dataflow. Permissions are defined per endpoint and
dataset type by Reportnet; see [docs/api-notes.md](docs/api-notes.md).

## Errors

```python
from reportnet import (AuthError, DiscoveryNotPermittedError,
                       DatasetLockedError, JobFailedError)

try:
    me.import_file(dataset_id=DATASET_ID, file=data).wait()
except DatasetLockedError:
    ...     # another job is running on this dataset
except DiscoveryNotPermittedError:
    ...     # key cannot enumerate datasets; use the identifier from the web UI
except AuthError:
    ...     # key invalid, or not permitted for this operation
except JobFailedError as e:
    ...     # job reached a terminal state other than FINISHED: e.status
```

| Exception | Cause |
|---|---|
| `AuthError` | HTTP 401 or 403 |
| `DiscoveryNotPermittedError` | Subclass of `AuthError`; enumeration not permitted |
| `DatasetLockedError` | HTTP 423, another job holds the dataset |
| `RateLimitError` | HTTP 429 |
| `JobFailedError` | Terminal job state other than `FINISHED` |
| `JobTimeoutError` | `wait()` exceeded its timeout |
| `CodelistResolutionError` | Raised only with `strict=True` |

Transport errors and 5xx responses on GET requests are retried up to three
times with exponential backoff. POST and PUT are not retried.

## Logging

The library logs to the `reportnet` logger and installs a `NullHandler`. No
output is produced unless logging is configured:

```python
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("reportnet").setLevel(logging.INFO)
```

| Level | Content |
|---|---|
| `DEBUG` | Each HTTP request and response, each job poll |
| `INFO` | Job state transitions, permission detection, code-list coverage |
| `WARNING` | Retries, failed jobs, and any fallback that weakens a result |

API keys are not written to log records.

A per-job callback is also available:

```python
job.wait(on_status=lambda status: print(status))
```

## Custodian operations

Available with an administrator key:

```python
flow = client.for_dataflow(DATAFLOW_ID)

flow.get_reporting_datasets()      # all reporters' datasets
flow.get_dataflow_contents()       # entire dataflow payload in one request
flow.dataset("Contacts")           # dataset lookup by table name
flow.to_mermaid()                  # structure diagram by submission status

ref = flow.reference_dataset("codelist")
flow.import_file(dataset_id=ref.id, file="codelists.csv", replace=True)
flow.set_reference_dataset_updatable(dataset_id=ref.id, updatable=False)

flow.list_historic_releases(dataset_id=DATASET_ID)
```

## Development

```bash
uv sync
uv run pytest
uv run pytest --integration      # live API; requires stored credentials
uv run ruff check src tests
uv run mypy src
uv run mkdocs serve
```

API behaviour, limitations and undocumented quirks are recorded in
[docs/api-notes.md](docs/api-notes.md). Example notebooks are in `notebooks/`.

## Changelog

[CHANGELOG.md](CHANGELOG.md). Before 1.0, breaking changes may occur in minor
releases and are listed with migration notes.

## Licence

[European Union Public Licence v1.2](LICENSE) (EUPL-1.2).

Copyright © European Environment Agency.
