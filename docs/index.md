# reportnet-client

Send your country's data to [Reportnet 3](https://reportnet.europa.eu) from
Python, instead of clicking through the website.

If you report data to the European Environment Agency — water, waste water, air,
nature — this library does the four things you need:

| | |
|---|---|
| **Look** | see which datasets are yours and what shape the data must be |
| **Upload** | send a spreadsheet, a CSV, or a DataFrame |
| **Check** | run Reportnet's quality rules and read what came back |
| **Download** | get data back out again |

Releasing your report is still done by a person on the Reportnet website. There
is no API for it, on purpose.

## Install

```bash
pip install "reportnet-client[dataframe] @ git+https://github.com/eea/reportnet-client.git"
```

Not on PyPI yet. `[dataframe]` lets you work with tables in pandas or polars —
most people want it. Two others you can add if you need them:

| Add | When you need it |
|---|---|
| `keyring` | keep your API key in your computer's password manager |
| `spatial` | your data has map geometry (shapes, points) |

## Your first upload

You need an **API key**. Get one from the Reportnet website: open your dataflow,
click the settings wheel, then **Generate new API-key**.

```python
import reportnet

# Connect, and say which country you are reporting for
flow = reportnet.ReportnetClient(api_key="your-key").for_dataflow(2003)
me = flow.find_reporter("FR")

# Which datasets are mine?
for d in me.get_reporting_datasets():
    print(d.id, d.table_name)

# Upload a table
me.import_frames(dataset_id=108952, frames={"Agglomerations": my_dataframe})

# Check it
result = me.validate(dataset_id=108952)
print(result.summary())
```

That is the whole loop. The guides below explain each step, and what to do when
Reportnet disagrees with you.

## Guides

Read these in order the first time.

1. **[Getting started](guides/getting-started.md)** — your key, connecting, and
   the one thing that confuses everybody
2. **[What Reportnet expects](guides/schema.md)** — tables, fields, and code lists
3. **[Uploading](guides/import.md)** — getting your data in
4. **[Checking your data](guides/validation.md)** — validation and its results
5. **[Downloading](guides/export.md)** — getting data back out
6. **[When something goes wrong](guides/troubleshooting.md)** — errors, in plain words

There is also a **[notebook](notebooks.md)** that walks the whole thing
end-to-end with real data, and an [API reference](api/client.md) if you want
the exact signatures.

## A note on how long things take

Uploads take seconds per table. **Validation can take twenty minutes** on a
large dataflow — that is Reportnet, not this library. Start it, go away, come
back. Never start a second validation while one is running; Reportnet refuses it
and shows an error on your dataflow.

## Keeping your key out of your code

```python
import reportnet

reportnet.save_key(dataflow_id=2003, api_key="your-key")   # once
client = reportnet.ReportnetClient.from_keyring(dataflow_id=2003)   # ever after
```

Needs the `keyring` extra. It uses your operating system's own password store.
