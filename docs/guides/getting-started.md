# Getting started

## Get an API key

On the Reportnet website, open your dataflow, click the settings wheel, and
choose **Generate new API-key**. Copy it somewhere safe.

## The one thing that confuses everybody

**Your key remembers what you were when you made it.**

Reportnet has two kinds of user:

- a **reporter** submits data for one country or organisation
- a **custodian** runs the dataflow

A key made while you were acting as a custodian is a *custodian key*. It cannot
upload report data — even if the very same person is also a reporter for that
country. Generating a new key does not change this. You have to make the key
from the reporter's view of the dataflow.

So if uploads fail with "Forbidden" and you are sure you have permission, this
is almost always why. Check which kind you have:

```python
flow = reportnet.ReportnetClient(api_key=key).for_dataflow(2003)
print(flow.capabilities().role)      # 'reporter' or 'custodian'
```

To upload report data, you want `reporter`.

## Connect

Say which dataflow, and which country you report for:

```python
import reportnet

flow = reportnet.ReportnetClient(api_key="your-key").for_dataflow(2003)
me = flow.find_reporter("FR")
```

`find_reporter()` takes the two-letter country code and works out the internal
"provider" number Reportnet wants on every request. You do not need to know that
number, but you do need this step — a reporter key that is not scoped to a
country is refused almost everywhere.

If your organisation is not a country, or two entries share a country code, list
them and pick:

```python
for r in flow.get_reporters():
    print(r.provider_id, r.country_code, r.country_name)

me = flow.for_provider(56)
```

## Find your datasets

A dataflow usually has more than one dataset — for example a tabular one and a
map one. Each has a number, and that number is what every later call needs.

```python
for d in me.get_reporting_datasets():
    print(d.id, d.table_name, d.status)
```

```
108952 Descriptive data PENDING
108957 Spatial data     PENDING
```

Write down the id for the dataset you are filling in. Everything else in these
guides takes it as `dataset_id`.

## Next

[What Reportnet expects](schema.md) — the shape your data has to be in.
