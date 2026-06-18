# Reference datasets

Reference datasets hold shared lookup and codelist data for a dataflow —
things like gas types, notation keys, or country codes. They are:

- managed by the **dataflow custodian** (no `provider_id`)
- shared across all reporters in the dataflow
- used as the source for `LINK` and `CODELIST` field types

## Import reference data

```python
df = client.for_dataflow(1619)   # custodian — no provider scope

df.import_file(
    dataset_id=REF_DATASET_ID,
    file="codelists.csv",
    replace=True,
)
```

## Lock and unlock

Lock the reference dataset to prevent edits during active reporting:

```python
# Lock (reporters can read but not write)
df.set_reference_dataset_updatable(dataset_id=REF_DATASET_ID, updatable=False)

# Unlock (allow custodian edits)
df.set_reference_dataset_updatable(dataset_id=REF_DATASET_ID, updatable=True)
```

## Export reference data

```python
frames = df.etl_export(dataset_id=REF_DATASET_ID).to_frames()
```

## Finding the reference dataset ID

The dataset ID appears in the Reportnet URL when you navigate to the
reference dataset tab in the UI:

```
https://reportnet.europa.eu/dataflow/1619/dataset/12345?tab=...
                                                     ^^^^^
                                               REF_DATASET_ID
```
