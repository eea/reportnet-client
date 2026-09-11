# reportnet-client

Send your country's data to [Reportnet 3](https://reportnet.europa.eu) from
Python, instead of clicking through the website.

If you report environmental data to the European Environment Agency, this
library lets you **look** at what is expected, **upload** your data, **check** it
against Reportnet's quality rules, and **download** it again.

If you **run** a dataflow, it covers the admin side as well — design datasets and
the ids quality rules are written against, reference data and code lists, job
history, and deletion. See
[for custodians](https://eea.github.io/reportnet-client/guides/custodians/).

📖 **[Full documentation](https://eea.github.io/reportnet-client/)**

> **Beta.** Some names may still change before version 1.0.

## Install

```bash
pip install "reportnet-client[dataframe] @ git+https://github.com/eea/reportnet-client.git"
```

Not on PyPI yet. `[dataframe]` adds pandas/polars support — most people want it.
Add `keyring` to keep your key in your computer's password manager, or `spatial`
if your data has map geometry.

## Get an API key

On the Reportnet website: open your dataflow → settings wheel →
**Generate new API-key**.

**Make the key from the reporter's view of the dataflow.** A key generated as a
custodian cannot upload report data, even if the same person also reports for
that country. This catches almost everyone once.

## The whole cycle

```python
import reportnet

# 1. Connect, and say which country you report for
flow = reportnet.ReportnetClient(api_key="your-key").for_dataflow(2003)
me = flow.find_reporter("FR")

# 2. Find your dataset
for d in me.get_reporting_datasets():
    print(d.id, d.table_name)          # 108952 Descriptive data

# 3. See what shape the data must be
schema = me.get_schema(dataset_id=108952)
table = schema.table("Agglomerations")
print(table.required_columns())

# 4. Upload — columns are matched to the schema for you
me.import_frames(
    dataset_id=108952,
    frames={"Agglomerations": my_dataframe},
    replace=True,
)

# 5. Check what landed
print(me.verify_import(dataset_id=108952))

# 6. Run Reportnet's quality rules (slow — minutes, not seconds)
result = me.validate(dataset_id=108952, timeout=1800)
print(result.summary())                # "8 issue(s) — 3 BLOCKER, 4 ERROR, 1 WARNING"

if result.has_blockers:
    print(result.to_frame())
```

Then a person presses **Release** on the Reportnet website. There is no API for
that step, by design.

## Three things worth knowing early

**Your key has a role.** Reporter or custodian, fixed when the key was made.
Uploading report data needs a reporter key. Check with
`flow.capabilities().role`.

**Validation is slow.** Twenty minutes is normal on a large dataflow. Never start
a second run while one is going — Reportnet refuses it and shows an error on your
dataflow. Read results with `get_validation_results()` instead, which starts
nothing.

**Validation results can be stale.** Reportnet serves the previous run's results
while a new one is going, with nothing in the response to say so. Check
`result.is_stale` before believing a number.

## Keeping your key out of your code

```python
reportnet.save_key(dataflow_id=2003, api_key="your-key")            # once
client = reportnet.ReportnetClient.from_keyring(dataflow_id=2003)   # ever after
```

Needs the `keyring` extra. Uses your operating system's password store.

## Learn more

| | |
|---|---|
| [Getting started](https://eea.github.io/reportnet-client/guides/getting-started/) | keys, connecting, finding your datasets |
| [What Reportnet expects](https://eea.github.io/reportnet-client/guides/schema/) | tables, fields, code lists |
| [Uploading](https://eea.github.io/reportnet-client/guides/import/) | files and DataFrames |
| [Checking your data](https://eea.github.io/reportnet-client/guides/validation/) | validation and its results |
| [When something goes wrong](https://eea.github.io/reportnet-client/guides/troubleshooting/) | errors in plain words |

There is also a [marimo notebook](notebooks/) that walks the whole cycle with
real data from a French submission.

## Licence

[European Union Public Licence v1.2](LICENSE) (EUPL-1.2).

Copyright © European Environment Agency.
