# Import data

## Basic import

```python
df = client.for_dataflow(1619)
ie = df.for_provider(42)   # reporter's provider_id

handle = ie.import_file(
    dataset_id=93953,
    file="data.csv",
)
handle.wait()
```

`.wait()` blocks until the import job finishes. It raises
[`JobFailedError`][reportnet.JobFailedError] if the job ends in any status
other than `FINISHED`.

## Replace vs append

```python
# Append rows (default)
ie.import_file(dataset_id=93953, file="new_rows.csv", replace=False)

# Replace all existing data
ie.import_file(dataset_id=93953, file="full_dataset.csv", replace=True)

# Or: delete first, then import
ie.delete_dataset_data(dataset_id=93953)
ie.import_file(dataset_id=93953, file="full_dataset.csv")
```

## Target a specific table

```python
ie.import_file(
    dataset_id=93953,
    file="table1a.csv",
    table_schema_id="68dd41f045f9450001260da7",  # from the Reportnet URL
)
```

## File formats accepted

| Type | Example |
|------|---------|
| File path | `"data.csv"` or `Path("data.csv")` |
| Raw bytes | `b"col1\|col2\n1\|2"` |
| File object | `open("data.csv", "rb")` |
| DataFrame | `polars.DataFrame(...)` or `pandas.DataFrame(...)` |

## Delimiter

The Reportnet API expects **pipe (`|`) as the default delimiter**, not commas.
This is the default in the library. Override it if needed:

```python
ie.import_file(dataset_id=93953, file="data.csv", delimiter=",")
```

## Importing from a DataFrame

```python
import polars as pl

data = pl.DataFrame({
    "category": ["Total including LULUCF"],
    "cyear": [2024],
    "gas": ["CO2"],
    "cvalue": [1234.5],
})

ie.import_file(
    dataset_id=93953,
    file=data,
    table_schema_id="68dd41f045f9450001260da7",
)
```

!!! note
    The `record_id` column must **not** be included — Reportnet assigns it on
    ingestion. Use [`get_schema()`](schema.md) to see which columns are expected.

## Progress callback

```python
handle = ie.import_file(dataset_id=93953, file="data.csv")
handle.wait(
    poll_interval=5.0,
    timeout=300.0,
    on_status=lambda s: print(f"import: {s}"),
)
```

## ETL import (Citus / JSON)

For Citus datasets only, you can push structured JSON directly:

```python
ie.etl_import(
    dataset_id=93953,
    tables=[{
        "tableSchemaId": "68dd41f0...",
        "records": [
            {"fields": [{"fieldSchemaId": "abc", "value": "Total"}]},
        ],
    }],
).wait()
```
