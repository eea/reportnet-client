# reportnet-client

Python client for the [EEA Reportnet 3 REST API](https://help.reportnet.europa.eu/rest-api/).

Fully type-annotated and ships a [PEP 561](https://peps.python.org/pep-0561/)
marker, so `mypy` and `pyright` check your calls against it.

!!! warning "Beta"
    The API may still change before 1.0.

## Installation

Not yet published to PyPI. Install from GitHub:

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

# Scope to a dataflow and reporter
flow = client.for_dataflow(1619)
ie = flow.find_reporter("IE")

# Look up a dataset by table name (requires administrator permissions)
ds = ie.dataset("Table1a")

# Upload, then download
ie.import_file(dataset_id=ds.id, file="ireland.csv").wait()
frames = ie.etl_export(dataset_id=ds.id).to_frames()
```

## Roles

Two key roles exist. Reporters submit data for one country or organisation.
Custodians administer a dataflow. Permissions differ between them and determine
which operations succeed. These guides are written for reporters; custodian
material is grouped separately.

## Guides

Ordered by the sequence in which they are used:

1. [Permissions](guides/capabilities.md). The key's role determines which
   operations are available, including why reporters take dataset identifiers
   from the web interface.
2. [Dataset schema](guides/schema.md). Tables, fields, code lists, and typed
   DataFrame templates.
3. [Import data](guides/import.md). Uploading a file, DataFrame, DuckDB
   relation or GeoDataFrame.
4. [Validate a dataset](guides/validation.md). Running Reportnet's validation
   rules and reading the results.
5. Release. Not available through the API; see
   [API notes](api-notes.md#there-is-no-release-endpoint). It must be performed
   in the web interface.

Custodian-only material: [Export data](guides/export.md) and
[Reference datasets](guides/reference-datasets.md).

## Secure key storage

Store API keys in the OS keychain (macOS Keychain, Windows Credential Manager,
libsecret) so they never appear in source code:

```python
import reportnet

# Production and sandbox keys are stored separately
reportnet.save_key(dataflow_id=1619, api_key="your-api-key")

# Load at runtime
client = reportnet.ReportnetClient.from_keyring(dataflow_id=1619)
```

Requires the `keyring` extra.

## Notes

Code lists are held in reference datasets. A dataflow may define several, and
only one contains the values for any given field.
[`get_template()`](guides/schema.md) selects it by schema coverage and warns
when resolution is incomplete. `strict=True` raises instead.

Imports, exports and validations are asynchronous and return a
[`JobHandle`](api/jobs.md). See [Logging](guides/logging.md) for progress
output.
