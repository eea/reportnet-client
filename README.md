# reportnet-client (Beta)

[![Tests](https://github.com/eea/reportnet-client/actions/workflows/tests.yml/badge.svg)](https://github.com/eea/reportnet-client/actions/workflows/tests.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

> **Beta** — the client may change and requires more testing before version 1.0.

Python client for the [EEA Reportnet 3 REST API](https://help.reportnet.europa.eu/rest-api/).

**[Full documentation](https://eea.github.io/reportnet-client/)**

## Contents

- [Installation](#installation)
- [Concepts](#concepts)
- [Environments](#environments)
- [Setup](#setup)
- [Reporter workflow](#reporter-workflow)
- [Discover the schema](#discover-the-schema)
- [Build data to upload](#build-data-to-upload)
- [Import data](#import-data)
- [Export data](#export-data)
- [Spatial data](#spatial-data)
- [Validate a dataset](#validate-a-dataset)
- [Reference datasets](#reference-datasets)
- [Custodian workflow](#custodian-workflow)
- [Job polling](#job-polling)
- [Release history](#release-history)
- [Dataset management](#dataset-management)
- [Provider helpers](#provider-helpers)
- [Error handling](#error-handling)
- [Development](#development)
- [Interactive notebooks](#interactive-notebooks)

## Installation

Not yet on PyPI — install directly from GitHub:

```bash
pip install git+https://github.com/eea/reportnet-client.git

# Optional: DataFrame support (polars, pandas, modin — via narwhals)
pip install "reportnet-client[dataframe] @ git+https://github.com/eea/reportnet-client.git"

# Optional: system keychain storage for API keys
pip install "reportnet-client[keyring] @ git+https://github.com/eea/reportnet-client.git"

# Optional: spatial/GeoDataFrame support (geopandas)
pip install "reportnet-client[spatial] @ git+https://github.com/eea/reportnet-client.git"
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
- Each **Reporter** (country or organisation) has one or more reporting **Datasets** per dataflow.
- **Reference Datasets** hold shared codelist/lookup values; they are not tied to a specific reporter.

## Environments

Two environments are available:

| Constant | URL |
|---|---|
| `reportnet.PRODUCTION_URL` | `https://api.reportnet.europa.eu` |
| `reportnet.SANDBOX_URL` | `https://sandbox.reportnet.europa.eu` |

The sandbox requires VPN access and uses separate API keys. By default the client connects to production.

## Setup

Your API key is generated in Reportnet under **Dataflow Settings → Generate new API key**.
One key typically covers a single dataflow.

### Secure key storage (recommended)

Store keys in the OS keychain (macOS Keychain, Windows Credential Manager, etc.)
so they never appear in source code:

```python
import reportnet

# Production key (default)
reportnet.save_key(dataflow_id=1619, api_key="your-api-key")

# Sandbox key — stored separately, won't collide with production
reportnet.save_key(dataflow_id=1619, api_key="your-sandbox-key", sandbox=True)

# Load at runtime — no key in code
client = reportnet.ReportnetClient.from_keyring(dataflow_id=1619)

# Sandbox client — picks sandbox URL and sandbox key automatically
client = reportnet.ReportnetClient.from_keyring(dataflow_id=1619, sandbox=True)
```

## Reporter workflow

If you are a **country reporter** (not a custodian), this is the typical flow:

```python
import reportnet

client = reportnet.ReportnetClient.from_keyring(dataflow_id=1619)
flow = client.for_dataflow(1619)

# Find your country using the ISO 3166-1 alpha-2 code — no need to know provider_id
ie = flow.find_reporter("IE")

# get_reporting_datasets() is automatically filtered to your country
datasets = ie.get_reporting_datasets()
# [ReportingDataset(id=93953, table_name='Table1a', status='PENDING'),
#  ReportingDataset(id=93954, table_name='Table7',  status='PENDING')]

# Work with a specific dataset
ds = datasets[0]
print(ds.id, ds.table_name, ds.status)
```

## Discover the schema

```python
schema = ie.get_schema(dataset_id=ds.id)

for table in schema.tables:
    print(table.name)
    print("  required:", table.required_columns())
    print("  all:     ", table.column_names())

# Inspect fields
table = schema.table("Table1a")
for field in table.fields:
    print(field.name, field.type.value, "required" if field.required else "")
# category  LINK            required
# cyear     NUMBER_INTEGER  required
# cvalue    NUMBER_DECIMAL
```

### Get typed DataFrame templates

`get_template()` does everything in one call: fetches the schema, auto-detects
the reference dataset, resolves codelists, and returns one empty DataFrame per
table with every column typed correctly.

```python
templates = ie.get_template(dataset_id=ds.id)
# {"Table1a": <empty polars.DataFrame>, "Table7": <empty polars.DataFrame>}

template = templates["Table1a"]
print(template.dtypes)
# category: Enum(['Total excluding LULUCF', 'Total including LULUCF', ...])
# cyear:    Int64
# cvalue:   Float64
```

LINK and CODELIST columns become `pl.Enum` (polars) or `CategoricalDtype` (pandas)
so invalid values are rejected immediately when you assign them — before the data
ever reaches the API.

If you need the codelists as a plain dict (e.g. to show users what values are
valid), call `get_codelists()` directly:

```python
ref_ds = flow.get_reference_datasets()[0]
codelists = ie.get_codelists(dataset_id=ds.id, ref_dataset_id=ref_ds.id)
# {"category": ["Total excluding LULUCF", "Total including LULUCF"], ...}
```

## Build data to upload

### From an Excel file

```python
import polars as pl

raw = pl.read_excel("my_data.xlsx", sheet_name="Table1a")
# or with pandas:
# import pandas as pd; raw = pd.read_excel("my_data.xlsx", sheet_name="Table1a")
```

Use `cast_frame()` to coerce the Excel types (e.g. floats where the schema wants
integers) and enforce Enum constraints in one step:

```python
templates = ie.get_template(dataset_id=ds.id)
typed = schema.table("Table1a").cast_frame(raw)
# cyear is now Int64; LINK columns are Enum — invalid values raise ValueError here
```

Or run `validate_frame()` if you'd rather get a list of errors than an exception:

```python
errors = schema.table("Table1a").validate_frame(typed)
if errors:
    for e in errors:
        print(e)
    raise SystemExit("Fix the errors above before uploading.")
```

### From a CSV file

```python
df = pl.read_csv("my_data.csv", separator="|")
```

### Built in Python

```python
import polars as pl

# Use the typed template to get Enum constraints on LINK columns
template = schema.table("Table1a").to_frame(codelists=codelists)

new_rows = pl.DataFrame({
    "category": ["Total including LULUCF", "Total excluding LULUCF"],
    "cyear":    [2024, 2024],
    "cvalue":   [1234.5, 5678.9],
}).cast({col: template.schema[col] for col in template.columns if col in ["category"]})
```

## Import data

```python
# From a file path
handle = ie.import_file(
    dataset_id=ds.id,
    file="my_data.csv",
    replace=False,          # append; set True to replace all existing rows
)
handle.wait()

# From a polars or pandas DataFrame (serialised with | delimiter by default)
handle = ie.import_file(dataset_id=ds.id, file=df)
handle.wait(poll_interval=5.0, timeout=300.0)

# From a DuckDB relation
import duckdb
con = duckdb.connect()
rel = con.sql("SELECT * FROM 'my_data.parquet'")
handle = ie.import_file(dataset_id=ds.id, file=rel)
handle.wait()
```

The default delimiter is `|` (pipe). Pass `delimiter=","` if your data uses commas.
Do **not** include a `record_id` column — Reportnet assigns that on ingestion.

### Multi-table import

`import_frames()` maps table names to DataFrames and uploads each one, waiting for
completion before starting the next. Table names must match the dataset schema.

```python
frames = {
    "Table1a": pl.DataFrame({"category": [...], "cyear": [...], ...}),
    "Table7":  pl.DataFrame({...}),
}
ie.import_frames(dataset_id=ds.id, frames=frames)
```

## Export data

All export methods return a `JobHandle`. Call `.result()` for raw bytes or `.to_frames()`
to get a `dict` of DataFrames (requires `reportnet-client[dataframe]`).

```python
# Full dataset export → dict of DataFrames, one per table
frames = ie.etl_export(dataset_id=ds.id).to_frames()
# {"Table1a": <polars.DataFrame>, "Table7": <polars.DataFrame>}

for name, frame in frames.items():
    print(name, frame.shape)

# Single-table export (CSV or XLSX)
handle = ie.export_file(dataset_id=ds.id, table_schema_id="abc123", mime_type="xlsx")
xlsx_bytes = handle.result()
```

`etl_export` automatically picks the correct API version for the dataflow backend:
v4 (ZIP of CSVs) for BigData/DLT2 dataflows, v3 (ZIP containing JSON) for Citus dataflows.

For analytics workflows, pass `version=5` to get a ZIP of Parquet files instead —
same shape as v4, smaller and faster to load. It's opt-in only (never auto-selected);
`to_frames()` handles it transparently:

```python
frames = ie.etl_export(dataset_id=ds.id, version=5).to_frames()
# {"Table1a": <polars.DataFrame>, "Table7": <polars.DataFrame>}
```

## Spatial data

Datasets with geometry fields (`POINT`, `POLYGON`, `MULTIPOLYGON`, etc.) store
values as WKT strings (v4 exports) or GeoJSON strings (v3 exports).
`to_geodataframe()` handles both formats automatically:

```bash
pip install "reportnet-client[spatial]"
```

```python
import reportnet

client = reportnet.ReportnetClient.from_keyring(1570)
flow = client.for_dataflow(1570)
fr = flow.find_reporter("FR")

# Export and convert to GeoDataFrame in two lines
frames = fr.etl_export(dataset_id=89259).to_frames()
gdf = reportnet.to_geodataframe(frames["ProtectedArea"], "geometry_polygon")

# Now use it as any geopandas GeoDataFrame
gdf.plot()
gdf.to_file("protected_areas.gpkg", driver="GPKG")
```

`to_geodataframe()` detects WKT vs GeoJSON automatically. The geometry column is
replaced in-place with parsed shapely geometries; all other columns are preserved.
The default CRS is `EPSG:4326`.

You can also upload a GeoDataFrame back to Reportnet — geometry is serialised as
WKT via geopandas' `.to_csv()`:

```python
fr.import_file(dataset_id=89259, file=gdf)
```

## Validate a dataset

`validate()` triggers a validation job, waits for it to finish, and returns a
`ValidationResult` — no manual polling needed.

```python
result = ie.validate(
    dataset_id=ds.id,
    poll_interval=10.0,
    timeout=600.0,
    on_status=lambda s: print(f"  {s}"),   # optional progress callback
)

print(result.summary())
# "dataset 93953: 3 issue(s) — 1 BLOCKER, 2 ERROR"

if result.has_blockers:
    print("Cannot submit — blockers found:")
    print(result.to_frame())   # polars/pandas DataFrame of all issues

result.ok          # True when no BLOCKER or ERROR issues
result.has_errors  # True when any BLOCKER or ERROR present
result.raw         # full API response dict
```

The `ValidationResult` columns returned by `.to_frame()`:
`level`, `entity_type`, `table`, `field`, `record_count`, `message`.

For lower-level control (e.g. polling separately from result retrieval):

```python
handle = ie.add_validation_job(dataset_id=ds.id)
handle.wait(poll_interval=10.0, timeout=600.0)
raw = ie.list_group_validations_dl(dataset_id=ds.id)
```

## Reference datasets

Reference datasets hold shared codelist data for a dataflow.
They have no reporter (`provider_id`) and can be locked to prevent edits
during active reporting periods.

```python
ref_ds = flow.get_reference_datasets()[0]

# Import new reference data (custodian only)
flow.import_file(dataset_id=ref_ds.id, file="codelists.csv", replace=True)

# Lock the reference dataset (prevent further edits)
flow.set_reference_dataset_updatable(dataset_id=ref_ds.id, updatable=False)
```

## Custodian workflow

Custodians work without a `provider_id` and can see all reporters:

```python
flow = client.for_dataflow(1619)

reporters = flow.get_reporters()
all_datasets = flow.get_reporting_datasets()  # all countries

# Scope to a specific reporter by country code
ie = flow.find_reporter("IE")

# Or by numeric provider_id (if you already know it)
ie = flow.for_provider(42)
```

## Job polling

All async calls return a `JobHandle`. You can poll manually or use `.wait()` / `.result()`:

```python
from reportnet import JobStatus

handle = ie.import_file(dataset_id=ds.id, file="data.csv")

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

## Release history

```python
releases = ie.list_historic_releases(dataset_id=ds.id)
for r in releases:
    print(r["releaseDate"], r.get("status"))
```

## Dataset management

```python
# Check whether an import is currently running
status = flow.check_import_process(dataset_id=ds.id)
# {"anyLockAssigned": True, "importInProgress": True}

# Delete all data before a full re-import
ie.delete_dataset_data(dataset_id=ds.id)

# Delete a single table's data
ie.delete_table_data(dataset_id=ds.id, table_schema_id="68dd41f0...")
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
from reportnet import AuthError, APIError, DatasetLockedError, JobFailedError, RateLimitError

try:
    handle = ie.import_file(dataset_id=ds.id, file="data.csv")
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
uv sync                       # create .venv and install all dev dependencies (installs reportnet-client)
uv run pytest                 # run unit tests (integration tests skipped)
uv run pytest --integration   # also run live API tests (requires keyring credentials)
uv run ruff check src tests
uv run mypy src
uv run mkdocs serve           # live-preview the documentation at http://127.0.0.1:8000

# Interactive notebooks (marimo)
uv sync --group explore
uv run marimo edit notebooks/01_explore_dataflow.py    # browse a dataflow interactively
uv run marimo edit notebooks/02_import_export_pipeline.py  # end-to-end import/export
uv run marimo edit notebooks/03_spatial_geodataframe.py    # spatial data → GeoDataFrame
```

## Interactive notebooks

Three [marimo](https://marimo.io) notebooks are included for interactive exploration:

| Notebook | Purpose |
|---|---|
| `notebooks/01_explore_dataflow.py` | Browse reporters, inspect schemas, visualise the dataflow structure, download empty templates |
| `notebooks/02_import_export_pipeline.py` | End-to-end import → validate → export workflow |
| `notebooks/03_spatial_geodataframe.py` | Export spatial data and convert to a geopandas GeoDataFrame |

### Run locally

```bash
# Install the explore group (marimo + polars); add geopandas for notebook 03
uv sync --group explore
pip install "reportnet-client[spatial]"   # for notebook 03

# Launch a notebook
uv run marimo edit notebooks/01_explore_dataflow.py
```

The notebook opens in your browser. Your API key is loaded from the system keychain automatically
(set it once with `reportnet.save_key(dataflow_id, "your-key")`). All three notebooks have a
**Sandbox** checkbox to connect to `sandbox.reportnet.europa.eu` instead of production.

### Static preview (read-only, no server needed)

```bash
# Export a self-contained HTML snapshot
uv run marimo export html notebooks/01_explore_dataflow.py -o docs/notebook_preview.html
```

The exported file can be committed and served via GitHub Pages as a static preview — useful for
sharing with colleagues who don't have Python installed. The preview is read-only (no live API
calls), but shows the notebook layout and all markdown documentation.
