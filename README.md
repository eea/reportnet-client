# reportnet-client (Beta)

[![Tests](https://github.com/eea/reportnet-client/actions/workflows/tests.yml/badge.svg)](https://github.com/eea/reportnet-client/actions/workflows/tests.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
[![Licence: EUPL-1.2](https://img.shields.io/badge/licence-EUPL--1.2-blue)](LICENSE)

> **Beta** — the client may change and requires more testing before version 1.0.

Python client for the [EEA Reportnet 3 REST API](https://help.reportnet.europa.eu/rest-api/).

**[Full documentation](https://eea.github.io/reportnet-client/)**

## Who this is for

This library is built for **Lead Reporters** — the people at a country or
organisation who prepare and submit data for a reporting obligation. That
workflow is the one it optimises for:

```
find your dataset  →  read its schema  →  build data  →  import  →  validate  →  fix  →  Release
└──────────────────────────── this library ────────────────────────────────┘   └── web UI ──┘
```

**Custodians** (dataflow administrators) can use it too, and get extra
capabilities their role unlocks — see [Custodian tasks](#custodian-tasks-admin).
But custodians already have dedicated tooling, so their needs are secondary
here.

**Your key's role changes what works, and how.** Reportnet grants permissions
per key, and a Lead Reporter key genuinely cannot do some things a custodian
key can. The library detects this and tells you — see
[What your key can do](#what-your-key-can-do). Notably, a Lead Reporter key
cannot list dataset IDs, so you take them from the web UI.

The package is fully type-annotated and ships a
[PEP 561](https://peps.python.org/pep-0561/) marker, so `mypy` and `pyright`
check your calls against it.

## Contents

**Lead Reporter workflow**
- [Installation](#installation)
- [Setup: your API key](#setup-your-api-key)
- [What your key can do](#what-your-key-can-do)
- [Step 1 — Find your dataset](#step-1--find-your-dataset)
- [Step 2 — Read the schema](#step-2--read-the-schema)
- [Step 3 — Build your data](#step-3--build-your-data)
- [Step 4 — Import](#step-4--import)
- [Step 5 — Validate](#step-5--validate)
- [Step 6 — Release (web UI only)](#step-6--release-web-ui-only)

**Reference**
- [Concepts](#concepts)
- [Export data](#export-data)
- [Spatial data](#spatial-data)
- [Job polling](#job-polling)
- [Error handling](#error-handling)
- [Logging](#logging)
- [Provider helpers](#provider-helpers)

**Other**
- [Custodian tasks (admin)](#custodian-tasks-admin)
- [Development](#development)
- [Interactive notebooks](#interactive-notebooks)
- [Changelog](#changelog) · [Licence](#licence)

## Installation

Not yet on PyPI — install directly from GitHub:

```bash
pip install git+https://github.com/eea/reportnet-client.git

# Recommended for reporters: DataFrame support (polars/pandas via narwhals)
pip install "reportnet-client[dataframe] @ git+https://github.com/eea/reportnet-client.git"

# Optional: system keychain storage for API keys
pip install "reportnet-client[keyring] @ git+https://github.com/eea/reportnet-client.git"

# Optional: spatial/GeoDataFrame support (geopandas)
pip install "reportnet-client[spatial] @ git+https://github.com/eea/reportnet-client.git"
```

## Setup: your API key

Generate it in Reportnet under **Dataflow Settings → Generate new API key**.
One key covers one dataflow.

Store it in the OS keychain so it never appears in source code:

```python
import reportnet

reportnet.save_key(dataflow_id=2003, api_key="your-api-key")

# Load at runtime — no key in code
client = reportnet.ReportnetClient.from_keyring(dataflow_id=2003)
flow = client.for_dataflow(2003)
```

Sandbox keys are stored separately (`sandbox=True` on both calls) and require
VPN access.

| Constant | URL |
|---|---|
| `reportnet.PRODUCTION_URL` | `https://api.reportnet.europa.eu` |
| `reportnet.SANDBOX_URL` | `https://sandbox.reportnet.europa.eu` |

## What your key can do

Reportnet has no endpoint that reports your key's role, so the library probes
for it — two cheap requests, cached:

```python
caps = flow.capabilities()
print(caps.summary())
# "dataflow 2003: reporter key; cannot discover dataset IDs"

caps.role                    # "custodian" | "reporter" | "none"
caps.can_discover_datasets   # False for Lead Reporter keys
caps.wants_provider_id       # True for Lead Reporter keys
```

Measured on a BigData dataflow with a Lead Reporter key:

| | Lead Reporter | Custodian |
|---|---|---|
| Read dataset schemas | ✅ | ✅ |
| Import data | ✅ | ✅ |
| Validate and read results | ✅ | ✅ |
| Check import status | ✅ | ✅ |
| **List dataset IDs** | ❌ take from web UI | ✅ |
| **Export / read data back** | ❌ | ✅ |
| Resolve codelists | ❌ (needs export) | ✅ |
| Release history | ❌ | ✅ |

Nothing here is a bug in the library or your key — it's how Reportnet assigns
permissions. The library raises `DiscoveryNotPermittedError` with an actionable
message rather than a bare `403` when you hit one of these.

## Step 1 — Find your dataset

**With a Lead Reporter key, take the dataset ID from the web UI.** Open your
dataset in Reportnet; the ID is in the URL:

```
https://reportnet.europa.eu/dataflow/2003/dataset/108953
                                                  ^^^^^^ your dataset_id
```

```python
it = flow.for_provider(64)      # your provider_id — 64 is Italy
DATASET_ID = 108953
```

Look up your `provider_id` by country code:

```python
reportnet.by_country("IT")      # [DataProvider(provider_id=64, country_code='IT', ...)]
```

If your key *can* discover datasets (custodian), look them up by name instead:

```python
ds = it.dataset("Descriptive data")     # raises DiscoveryNotPermittedError for reporter keys
it.datasets_by_table()                  # {"Descriptive data": ..., "Spatial data": ...}
```

## Step 2 — Read the schema

This works with any key, given a dataset ID:

```python
schema = it.get_schema(dataset_id=DATASET_ID)

for table in schema.tables:
    print(table.name, "required:", table.required_columns())

table = schema.table("Reporter")
for field in table.fields:
    print(field.name, field.type.value, "required" if field.required else "")
```

### Typed DataFrame templates

`get_template()` returns one empty, correctly-typed DataFrame per table:

```python
templates = it.get_template(dataset_id=DATASET_ID)
print(templates["Reporter"].dtypes)
```

Numeric, date and boolean columns are always typed. `LINK`/`CODELIST` columns
become `pl.Enum` (polars) or `CategoricalDtype` (pandas) **only if the codelists
can be resolved**, which requires export rights — so with a Lead Reporter key
they stay plain strings and you get a warning saying so. Pass `strict=True` to
make that an error instead:

```python
templates = it.get_template(dataset_id=DATASET_ID, strict=True)
```

The library never hands back a template that silently accepts anything.

## Step 3 — Build your data

```python
import polars as pl

raw = pl.read_excel("my_data.xlsx", sheet_name="Reporter")
# or pl.read_csv("my_data.csv", separator="|")
```

Coerce it to the schema's types — this raises on values that don't fit:

```python
typed = schema.table("Reporter").cast_frame(raw)
```

Or collect errors instead of raising:

```python
errors = schema.table("Reporter").validate_frame(typed)
if errors:
    raise SystemExit("\n".join(errors))
```

Do **not** include a `record_id` column — Reportnet assigns it.

## Step 4 — Import

```python
handle = it.import_file(
    dataset_id=DATASET_ID,
    file=typed,                    # path, bytes, DataFrame, DuckDB relation or GeoDataFrame
    table_schema_id=schema.table("Reporter").id,
    replace=False,                 # True replaces all existing rows
)
handle.wait(poll_interval=5.0, timeout=600.0)
```

The default delimiter is `|`; pass `delimiter=","` if your data uses commas.

`providerId` is handled for you. Whether Reportnet requires or rejects it
depends on your key's role, so the library infers it and retries with the other
option if the inference was wrong.

Multiple tables at once:

```python
it.import_frames(dataset_id=DATASET_ID, frames={"Reporter": df1, "Contacts": df2})
```

> **A FINISHED job does not prove the data landed.** Reportnet can accept a
> request, run it, report FINISHED and write nothing — for example when records
> are missing a required `countryCode`. With a Lead Reporter key you cannot
> export to check, so confirm in the web UI.

## Step 5 — Validate

```python
result = it.validate(dataset_id=DATASET_ID, poll_interval=10.0, timeout=600.0)

print(result.summary())        # "dataset 108953: 3 issue(s) — 1 BLOCKER, 2 ERROR"
if result.has_blockers:
    print(result.to_frame())   # DataFrame of all issues

result.ok          # True when no BLOCKER or ERROR
result.raw         # full API response
```

The right backend endpoint is chosen for you. If another job is running you'll
get `DatasetLockedError` — wait and retry.

## Step 6 — Release (web UI only)

**There is no API endpoint that releases or submits a dataset.** Verified across
all 13 Swagger service specs and all three help-documentation categories. You
can automate everything up to and including validation, but a human must press
**Release** in the Reportnet web interface.

See [API notes](https://eea.github.io/reportnet-client/api-notes/) for the
evidence and other API limitations.

## Concepts

```
Dataflow  (a reporting obligation, e.g. "UWWTD")
  └── Reporter / DataProvider  (a country or organisation — you)
        └── Dataset  (your data, one per table schema)
              └── Table / Field
  └── Reference Dataset  (shared codelists, no reporter)
```

Two storage backends exist — **Citus** and **BigData (DLT2)**. The library picks
the right endpoints and API versions for you; `flow.is_big_dataflow()` reports
which, when your key can read it.

## Export data

Requires export rights — **not available to Lead Reporter keys** on the
dataflows measured so far.

```python
frames = flow.etl_export(dataset_id=DATASET_ID).to_frames()
# {"Reporter": <polars.DataFrame>, ...}
```

The API version is auto-selected (v4 for BigData, v3 for Citus). Pass
`version=5` for a ZIP of Parquet, which is smaller and faster to load.

## Spatial data

Geometry fields round-trip as WKT (v4 exports) or GeoJSON (v3);
`to_geodataframe()` detects which.

```bash
pip install "reportnet-client[spatial]"
```

```python
frames = flow.etl_export(dataset_id=89259).to_frames()
gdf = reportnet.to_geodataframe(frames["ProtectedArea"], "geometry_polygon")
gdf.plot()
```

A `GeoDataFrame` can be imported directly — geometry is serialised as WKT.

## Job polling

Imports, exports and validations are asynchronous and return a `JobHandle`:

```python
handle.status()                                    # single poll
handle.wait(poll_interval=5.0, timeout=300.0,
            on_status=lambda s: print(s))          # block until terminal
```

Terminal statuses: `FINISHED`, `FAILED`, `REFUSED`, `CANCELED`,
`CANCELED_BY_ADMIN`. `.wait()` raises `JobFailedError` on anything but
`FINISHED`.

## Error handling

```python
from reportnet import (AuthError, DiscoveryNotPermittedError, APIError,
                       DatasetLockedError, JobFailedError, RateLimitError)

try:
    it.import_file(dataset_id=DATASET_ID, file="data.csv").wait()
except DiscoveryNotPermittedError as e:
    print(e)                       # explains how to get the ID from the web UI
except DatasetLockedError:
    print("another job is running — try again shortly")
except AuthError:
    print("key invalid, or not permitted for this operation")
except JobFailedError as e:
    print(f"job {e.job_id} ended with {e.status}")
```

`DiscoveryNotPermittedError` subclasses `AuthError`, so existing handlers keep
working. `CodelistResolutionError` is raised only when you pass `strict=True`.

Transient network errors and 5xx responses on GET are retried automatically
(3 times, exponential back-off). POST and PUT are not, to avoid duplicate jobs.

## Logging

Silent until you opt in:

```python
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("reportnet").setLevel(logging.DEBUG)
```

| Level | What you get |
|---|---|
| `DEBUG` | every HTTP request/response, every job poll |
| `INFO` | job transitions with elapsed time, capability detection, codelist coverage |
| `WARNING` | retries, failed jobs, and any fallback that weakens a result |

API keys are never written to a log record.

## Provider helpers

```python
from reportnet import by_id, by_country, by_group

by_country("IT")       # [DataProvider(provider_id=64, ...)]
by_id(64)              # DataProvider(provider_id=64, country_code='IT', ...)
by_group("EEA")        # all EEA member providers
```

Most countries appear twice with different IDs — check which your dataflow uses.

## Custodian tasks (admin)

Custodians administer a dataflow rather than report to it, and have dedicated
tooling elsewhere. What this library adds, given a custodian key:

```python
flow = client.for_dataflow(2003)          # no provider scope

flow.get_reporters()                      # every country registered
flow.get_reporting_datasets()             # every reporter's datasets
flow.get_dataflow_contents()              # all of the above in ONE request
flow.to_mermaid()                         # diagram, coloured by submission status
```

Reference datasets (shared codelists):

```python
ref = flow.reference_dataset("codelist")
flow.import_file(dataset_id=ref.id, file="codelists.csv", replace=True)
flow.set_reference_dataset_updatable(dataset_id=ref.id, updatable=False)
```

Dataset management:

```python
flow.delete_dataset_data(dataset_id=DATASET_ID)
flow.delete_table_data(dataset_id=DATASET_ID, table_schema_id="...")
flow.list_historic_releases(dataset_id=DATASET_ID)
```

## Development

```bash
uv sync                       # create .venv and install dev dependencies
uv run pytest                 # unit tests (integration skipped)
uv run pytest --integration   # also live API tests (needs keyring credentials)
uv run ruff check src tests
uv run mypy src
uv run mkdocs serve
```

## Interactive notebooks

Three [marimo](https://marimo.io) notebooks under `notebooks/`:

| Notebook | Purpose |
|---|---|
| `01_explore_dataflow.py` | Browse reporters, schemas, dataflow structure |
| `02_import_export_pipeline.py` | End-to-end import → validate → export |
| `03_spatial_geodataframe.py` | Spatial data → GeoDataFrame |

```bash
uv sync --group explore
uv run marimo edit notebooks/01_explore_dataflow.py
```

## Changelog

Release history is in [CHANGELOG.md](CHANGELOG.md). While the version is below
1.0, breaking changes may land in a minor release — they're always listed under
**Changed** with a migration note.

## Licence

Licensed under the [European Union Public Licence v1.2](LICENSE) (EUPL-1.2).

Copyright © European Environment Agency.
