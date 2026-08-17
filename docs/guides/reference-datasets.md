# Reference datasets

Reference datasets hold shared lookup and codelist data for a dataflow —
things like gas types, notation keys, or country codes. They are:

- managed by the **dataflow custodian** (no `provider_id`)
- shared across all reporters in the dataflow
- used as the source for `LINK` and `CODELIST` field types

## Import reference data

```python
flow = client.for_dataflow(1619)   # custodian — no provider scope

flow.import_file(
    dataset_id=REF_DATASET_ID,
    file="codelists.csv",
    replace=True,
)
```

## Lock and unlock

Lock the reference dataset to prevent edits during active reporting:

```python
# Lock (reporters can read but not write)
flow.set_reference_dataset_updatable(dataset_id=REF_DATASET_ID, updatable=False)

# Unlock (allow custodian edits)
flow.set_reference_dataset_updatable(dataset_id=REF_DATASET_ID, updatable=True)
```

## Export reference data

```python
frames = flow.etl_export(dataset_id=REF_DATASET_ID).to_frames()
```

## Resolve LINK field codelists

Reporting datasets use `LINK` fields to reference values from a reference dataset.
`get_codelists()` exports the reference dataset and maps each LINK field in the
reporting dataset to its sorted list of valid values:

```python
codelists = flow.get_codelists(dataset_id=93953, ref_dataset_id=REF_DATASET_ID)
# {"category": ["Total excluding LULUCF", "Total including LULUCF"],
#  "scenario": ["WAM", "WEM", "WOM"],
#  "ry": ["0", "1"]}
```

Pass the result to `to_frame()` to get LINK columns as `pl.Enum` (polars) or
`CategoricalDtype` (pandas), which enforces valid values at assignment time:

```python
schema = flow.get_schema(dataset_id=93953)
template = schema.table("Table1a").to_frame(codelists=codelists)
```

See the [Schema guide](schema.md#link-fields-resolving-valid-values) for more detail.

## Finding the right reference dataset

A dataflow usually has **several** reference datasets, and each LINK field
resolves from only one of them. Picking the wrong one doesn't fail — it just
resolves nothing.

On production dataflow 2003, the spatial dataset's 10 LINK fields resolve like
this:

| Reference dataset | LINK fields covered |
|---|---|
| Spatial reference data | 0 |
| Descriptive reference data | 0 |
| **Spatial codelist** | **10** |
| Descriptive codelist | 0 |

So the first one in the list covers nothing at all.

**Let the library choose.** [`get_template()`](schema.md) compares schemas and
picks the reference dataset that actually covers your fields — no export jobs
needed to work it out:

```python
templates = ie.get_template(dataset_id=93953)   # picks the right one for you
```

**Look one up by name** when you do want a specific dataset. Matching is
case-insensitive and accepts a substring:

```python
ref = flow.reference_dataset("codelist")     # "Reference Dataset - Codelist"
codelists = ie.get_codelists(dataset_id=93953, ref_dataset_id=ref.id)
```

An ambiguous or unknown name raises `KeyError` listing the candidates, so you
never silently get the wrong one.

**Or read the ID from the UI** — it appears in the Reportnet URL when you open
the reference dataset tab:

```
https://reportnet.europa.eu/dataflow/1619/dataset/12345?tab=...
                                                  ^^^^^
                                            REF_DATASET_ID
```
