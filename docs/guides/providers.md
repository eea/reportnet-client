# Provider helpers

Every reporter in Reportnet has a numeric `provider_id`. The library ships a
built-in lookup table so you can find IDs without hitting the API.

## Look up by ID

```python
from reportnet import by_id

p = by_id(42)
# DataProvider(provider_id=42, country_code='AD', name='Andorra', eea_group='Other', eurostat_group='Other')
```

## Look up by country code

```python
from reportnet import by_country

providers = by_country("IE")
# [DataProvider(provider_id=..., country_code='IE', name='Ireland', ...)]
```

A country may appear more than once (e.g. if it has both a primary and an
additional entry in Reportnet). Check `provider_id` against the value in
[`get_reporters()`][reportnet.DataflowClient.get_reporters] to find the right one
for a specific dataflow.

## Filter by group

```python
from reportnet import by_group

# All EEA member countries
eea = by_group("EEA")

# EU member states (using Eurostat classification)
eu = by_group("EU", field="eurostat_group")

# EEA cooperating countries
coop = by_group("EEA Cooperating country")
```

`field` defaults to `"eea_group"`. Use `"eurostat_group"` for Eurostat-style
groupings.

## All providers

```python
from reportnet import PROVIDERS

for p in PROVIDERS:
    print(p.provider_id, p.country_code, p.name)
```

## Get reporters for a dataflow

For the authoritative list of which providers are active in a specific dataflow
(including their assigned dataset IDs), use the API:

```python
reporters = client.for_dataflow(1619).get_reporters()
for r in reporters:
    print(r.provider_id, r.dataset_id)
```
