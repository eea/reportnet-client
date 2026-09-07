# reportnet-client (Beta)

[![Tests](https://github.com/eea/reportnet-client/actions/workflows/tests.yml/badge.svg)](https://github.com/eea/reportnet-client/actions/workflows/tests.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
[![Licence: EUPL-1.2](https://img.shields.io/badge/licence-EUPL--1.2-blue)](LICENSE)

> **Beta** — the client may change before version 1.0.

Prepare, upload and validate your country's data for
[EEA Reportnet 3](https://reportnet.europa.eu) from Python, instead of clicking
through the web interface.

**[Full documentation](https://eea.github.io/reportnet-client/)**

## Who this is for

**Reporters** — the people at a country or organisation who prepare and submit
data for a reporting obligation. Your whole job looks like this:

```
connect  →  read the schema  →  prepare data  →  upload  →  validate  →  fix  →  Release
└─────────────────────── you can script all of this ──────────────────┘  └── web UI ──┘
```

The last step stays in the browser: Reportnet has no way to submit a dataset
from code, so a person always presses **Release**.

**Custodians** (dataflow administrators) can use the library too — see
[Custodian tasks](#custodian-tasks-admin) — but they have their own tooling, so
this guide is written for reporters.

## Contents

- [Install](#install) · [Your API key](#your-api-key)
- [The whole workflow](#the-whole-workflow) — a complete example
- **Step by step:** [Connect](#step-1--connect) · [Find your dataset](#step-2--find-your-dataset) · [Read the schema](#step-3--read-the-schema) · [Prepare your data](#step-4--prepare-your-data) · [Upload](#step-5--upload) · [Check it landed](#step-6--check-it-landed) · [Validate](#step-7--validate) · [Release](#step-8--release)
- [When something goes wrong](#when-something-goes-wrong) · [What your key can do](#what-your-key-can-do)
- [Download your data back](#download-your-data-back) · [Seeing what's happening](#seeing-whats-happening)
- [Custodian tasks (admin)](#custodian-tasks-admin)
- [Development](#development) · [Changelog](#changelog) · [Licence](#licence)

## Install

```bash
pip install "reportnet-client[dataframe,keyring] @ git+https://github.com/eea/reportnet-client.git"
```

That includes everything a reporter needs: table handling and secure key
storage. Add `spatial` if your data has map geometry:

```bash
pip install "reportnet-client[dataframe,keyring,spatial] @ git+https://github.com/eea/reportnet-client.git"
```

## Your API key

In Reportnet, open your dataflow and go to **Dataflow Settings → Generate new
API key**. One key covers one dataflow.

Save it once into your computer's keychain, so it never sits in your code:

```python
import reportnet

reportnet.save_key(dataflow_id=1234, api_key="paste-your-key-here")
```

From then on your scripts just load it:

```python
client = reportnet.ReportnetClient.from_keyring(dataflow_id=1234)
```

There is a separate sandbox environment for testing, which needs its own key
and a VPN connection — pass `sandbox=True` to both calls to use it.

## The whole workflow

A complete, working script. Each piece is explained below.

```python
import polars as pl
import reportnet

DATAFLOW_ID = 1234          # from the Reportnet URL
DATASET_ID  = 56789         # from the Reportnet URL — see Step 2
COUNTRY     = "IT"          # your country code

client = reportnet.ReportnetClient.from_keyring(dataflow_id=DATAFLOW_ID)
me = client.for_dataflow(DATAFLOW_ID).find_reporter(COUNTRY)

# What does this dataset expect?
schema = me.get_schema(dataset_id=DATASET_ID)
table = schema.table("Contacts")

# Prepare and check your data before sending it
data = pl.read_excel("my_data.xlsx", sheet_name="Contacts")
data = table.cast_frame(data)

# Upload, then confirm it arrived
me.import_file(dataset_id=DATASET_ID, file=data, table_schema_id=table.id).wait()
print(me.verify_import(dataset_id=DATASET_ID)["Contacts"])

# Run Reportnet's checks
result = me.validate(dataset_id=DATASET_ID)
print(result.summary())
```

## Step 1 — Connect

Identify yourself by country code. You don't need to know any internal ID
numbers:

```python
client = reportnet.ReportnetClient.from_keyring(dataflow_id=DATAFLOW_ID)
flow = client.for_dataflow(DATAFLOW_ID)

me = flow.find_reporter("IT")        # your ISO country code
```

If the code isn't registered for this dataflow, the error lists the ones that
are. To see them yourself:

```python
for r in flow.get_reporters():
    print(r.country_code, r.country_name)
```

## Step 2 — Find your dataset

**Take the dataset ID from the Reportnet website.** Open your dataset; the
number is in the address bar:

```
https://reportnet.europa.eu/dataflow/1234/dataset/56789
                                                  ^^^^^ this is your dataset ID
```

A dataflow usually gives you one dataset per group of tables, so you may have
two or three. Note the numbers once and keep them in your script.

> Reportnet doesn't let a reporter's key list dataset IDs — only administrators
> can do that. This is a permission rule, not a limitation of the library, so
> the website is the place to look them up.

## Step 3 — Read the schema

The schema tells you which tables and columns are expected, and which are
mandatory:

```python
schema = me.get_schema(dataset_id=DATASET_ID)

for table in schema.tables:
    print(table.name, "— required:", table.required_columns())
```

### Start from a ready-made template

`get_template()` gives you an empty table per sheet, already set up with the
right column names and types:

```python
templates = me.get_template(dataset_id=DATASET_ID)
templates["Contacts"]        # empty, correctly typed
```

Some columns only accept values from an official code list. The library fills
those in when it can; when it can't, it tells you rather than quietly letting
anything through. Add `strict=True` if you'd rather that stopped your script:

```python
templates = me.get_template(dataset_id=DATASET_ID, strict=True)
```

## Step 4 — Prepare your data

Read your spreadsheet or CSV:

```python
import polars as pl

data = pl.read_excel("my_data.xlsx", sheet_name="Contacts")
```

Then fit it to the schema. `cast_frame()` converts columns to the expected
types and fails if something can't be converted — better to find out now than
after uploading:

```python
data = schema.table("Contacts").cast_frame(data)
```

If you'd rather see a list of problems than have it stop:

```python
for problem in schema.table("Contacts").validate_frame(data):
    print(problem)
```

Don't add a `record_id` column — Reportnet creates that itself.

## Step 5 — Upload

```python
table = schema.table("Contacts")

job = me.import_file(dataset_id=DATASET_ID, file=data, table_schema_id=table.id)
job.wait()
```

Uploads run in the background, so `wait()` blocks until Reportnet finishes.
Add `replace=True` to clear the table first instead of adding to it.

You can also pass a file path directly (`file="my_data.csv"`), and upload
several tables in one go:

```python
me.import_frames(dataset_id=DATASET_ID, frames={"Contacts": df1, "Sites": df2})
```

## Step 6 — Check it landed

**An upload can finish successfully and still store nothing** — for example if
rows are missing a value Reportnet requires. Always confirm:

```python
me.verify_import(dataset_id=DATASET_ID)["Contacts"]
# {'records': 42, 'last_import': datetime(...), 'file_extension': 'csv'}
```

`records` tells you how many rows actually arrived. If it's `0` or `None` when
you expected data, something was rejected silently — check the file for missing
mandatory columns.

## Step 7 — Validate

This runs Reportnet's own quality checks, the same ones the website runs:

```python
result = me.validate(dataset_id=DATASET_ID)

print(result.summary())
# "dataset 56789: 3 issue(s) — 1 BLOCKER, 2 ERROR"

if result.has_blockers:
    print(result.to_frame())      # every issue, as a table
```

Validation can take a few minutes on large datasets. `result.ok` is `True` when
there's nothing blocking your submission.

If you get a "dataset locked" message, another job is still running — wait a
moment and try again.

## Step 8 — Release

**This step is not available from Python.** Reportnet has no way to submit a
dataset programmatically, so once your data is uploaded and validation is
clean, open the dataflow in the website and press **Release**.

Everything up to that point can be automated and repeated.

## When something goes wrong

```python
from reportnet import (AuthError, DiscoveryNotPermittedError,
                       DatasetLockedError, JobFailedError)

try:
    me.import_file(dataset_id=DATASET_ID, file=data).wait()
except DatasetLockedError:
    print("Another job is running on this dataset — try again shortly.")
except DiscoveryNotPermittedError as e:
    print(e)      # explains how to find the ID on the website
except AuthError:
    print("Your key is invalid, or not allowed to do this.")
except JobFailedError as e:
    print(f"Reportnet rejected the job: {e.status}")
```

Common situations:

| What you see | What it usually means |
|---|---|
| "not authorised" when listing datasets | Normal for a reporter key — get the ID from the website |
| Dataset locked | A validation or import is still running |
| Upload finished but `records` is 0 | Rows were rejected — check mandatory columns |
| Code-list columns accept anything | Your key can't read the shared code lists; values are checked at validation instead |

Temporary network problems are retried automatically.

## What your key can do

Reportnet gives reporters and administrators different permissions. The library
works out which you have:

```python
print(flow.capabilities().summary())
# "dataflow 1234: reporter key; cannot discover dataset IDs"
```

| | Reporter | Administrator |
|---|---|---|
| Read the schema | ✅ | ✅ |
| Upload data | ✅ | ✅ |
| Confirm an upload landed | ✅ | ✅ |
| Validate and read results | ✅ | ✅ |
| Look up your country by code | ✅ | ✅ |
| Download your own data back out | ✅ | ✅ |
| List dataset IDs | website only | ✅ |
| Download shared code lists | ❌ | ✅ |
| Fill in code-list columns automatically | ❌ | ✅ |

None of the ❌ rows are faults — they're how Reportnet assigns permissions.

## Download your data back

You can read your own dataset back out — useful to check what Reportnet
actually holds, or to start from last year's submission:

```python
tables = me.etl_export(dataset_id=DATASET_ID).to_frames()
tables["Contacts"]        # a normal DataFrame
```

This runs in the background and can take a few minutes on a large dataset.

### Spatial data

If your data has map geometry, it converts to a GeoDataFrame in one step (needs
the `spatial` extra):

```python
gdf = reportnet.to_geodataframe(tables["ProtectedArea"], "geometry_polygon")
gdf.plot()
```

You can upload a GeoDataFrame straight back with `import_file()`.

## Seeing what's happening

Long uploads and validations can look like nothing is happening. Turn on
progress messages:

```python
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("reportnet").setLevel(logging.INFO)
```

You'll see each job start, change state and finish, plus warnings whenever the
library has to fall back to something less precise. Your API key is never
written to the log.

For a progress callback instead:

```python
job.wait(on_status=lambda status: print(status))
```

## Custodian tasks (admin)

With an administrator key you also get the dataflow-wide view:

```python
flow = client.for_dataflow(DATAFLOW_ID)

flow.get_reporting_datasets()      # every country's datasets
flow.get_dataflow_contents()       # everything about the dataflow, in one call
flow.dataset("Contacts")           # look datasets up by name
flow.to_mermaid()                  # diagram coloured by submission status
```

Managing shared code lists and reading release history are administrator-only
(reporters can export their own data, but not the shared reference datasets):

```python
ref = flow.reference_dataset("codelist")
flow.import_file(dataset_id=ref.id, file="codelists.csv", replace=True)
flow.set_reference_dataset_updatable(dataset_id=ref.id, updatable=False)

flow.list_historic_releases(dataset_id=DATASET_ID)
```

## Development

```bash
uv sync                       # set up the environment
uv run pytest                 # tests
uv run pytest --integration   # also test against the live API
uv run ruff check src tests
uv run mypy src
uv run mkdocs serve           # preview the documentation
```

Notes on the API's quirks and limitations are in
[docs/api-notes.md](docs/api-notes.md). Example notebooks are in `notebooks/`.

## Changelog

See [CHANGELOG.md](CHANGELOG.md). Until version 1.0, breaking changes can land
in a minor release and are always listed with a note on what to change.

## Licence

Licensed under the [European Union Public Licence v1.2](LICENSE) (EUPL-1.2).

Copyright © European Environment Agency.
