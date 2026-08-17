# reportnet-client

Python client for the [EEA Reportnet 3 REST API](https://help.reportnet.europa.eu/rest-api/).

Fully type-annotated and ships a [PEP 561](https://peps.python.org/pep-0561/)
marker, so `mypy` and `pyright` check your calls against it.

!!! warning "Beta"
    The API may still change before 1.0.

## Installation

Not yet on PyPI — install from GitHub:

```bash
pip install git+https://github.com/eea/reportnet-client.git
```

Optional extras (combine as needed, e.g. `[dataframe,keyring]`):

| Extra | Adds | For |
|---|---|---|
| `dataframe` | narwhals, polars | DataFrame import/export, typed templates |
| `keyring` | keyring | API keys in the OS keychain |
| `spatial` | geopandas | Geometry columns as GeoDataFrames |

```bash
pip install "reportnet-client[dataframe,keyring] @ git+https://github.com/eea/reportnet-client.git"
```

## Quick start

```python
import reportnet

client = reportnet.ReportnetClient(api_key="your-api-key")

# Scope to a dataflow, then to your country
flow = client.for_dataflow(1619)
ie = flow.find_reporter("IE")

# Find a dataset by table name — no list-index guessing
ds = ie.dataset("Table1a")

# Import a CSV, then export back to DataFrames
ie.import_file(dataset_id=ds.id, file="ireland.csv").wait()
frames = ie.etl_export(dataset_id=ds.id).to_frames()
```

## The reporting workflow

The guides follow the order you'd actually work in:

1. **[Dataset schema](guides/schema.md)** — discover the tables, fields and
   codelists you must match, and get typed, empty DataFrame templates.
2. **[Import data](guides/import.md)** — upload a file, DataFrame, DuckDB
   relation or GeoDataFrame.
3. **[Validate a dataset](guides/validation.md)** — run Reportnet's rules and
   read the results as a DataFrame.
4. **[Export data](guides/export.md)** — pull data back out, as bytes or
   DataFrames.
5. **Release** — **not available through the API.** See
   [API notes](api-notes.md#there-is-no-release-endpoint); you must press
   *Release* in the Reportnet web UI.

Supporting material: [Reference datasets](guides/reference-datasets.md),
[Provider helpers](guides/providers.md), [Logging](guides/logging.md).

## Secure key storage

Store API keys in the OS keychain (macOS Keychain, Windows Credential Manager,
libsecret) so they never appear in source code:

```python
import reportnet

# Save once — production and sandbox keys are stored separately
reportnet.save_key(dataflow_id=1619, api_key="your-api-key")

# Load at runtime
client = reportnet.ReportnetClient.from_keyring(dataflow_id=1619)
```

Requires the `keyring` extra.

## Two things worth knowing early

**Codelists come from a specific reference dataset.** A dataflow often has
several, and only one holds the lookup values for any given field.
[`get_template()`](guides/schema.md) works out which and warns you if it can't —
it never hands back a template that silently accepts anything. Pass
`strict=True` to turn that warning into an error.

**Long jobs are asynchronous.** Imports, exports and validations return a
[`JobHandle`](api/jobs.md) you poll. Turn on [logging](guides/logging.md) to see
what's happening during a long wait.
