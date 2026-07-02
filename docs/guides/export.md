# Export data

All export methods return a [`JobHandle`][reportnet.JobHandle]. The job runs
in the background; call `.result()` for raw bytes or `.to_frames()` to get
DataFrames directly.

## ETL export — ZIP of CSVs (recommended)

Returns a ZIP archive with one CSV per table.

```python
ie = client.for_dataflow(1619).for_provider(42)

handle = ie.etl_export(dataset_id=93953)
zip_bytes = handle.result(poll_interval=10.0, timeout=600.0)

with open("export.zip", "wb") as f:
    f.write(zip_bytes)
```

## Export directly to DataFrames

Requires `pip install "reportnet[dataframe]"`.

```python
frames = ie.etl_export(dataset_id=93953).to_frames(poll_interval=10.0, timeout=600.0)
# {"Table1a": <polars.DataFrame>, "Table1b": <polars.DataFrame>}

for name, frame in frames.items():
    print(name, frame.shape)
    print(frame.head())
```

`to_frames()` tries polars first, falls back to pandas.

## Progress callback

```python
frames = ie.etl_export(dataset_id=93953).to_frames(
    poll_interval=10.0,
    timeout=600.0,
    on_status=lambda s: print(f"export: {s}"),
)
```

## ETL export v5 — Parquet

Use `version=5` to receive Parquet files instead of CSVs — same shape as v4,
smaller and faster to load. It's opt-in only and never chosen automatically.
`to_frames()` handles it transparently, same as v4:

```python
frames = ie.etl_export(dataset_id=93953, version=5).to_frames(poll_interval=10.0, timeout=600.0)
# {"Table1a": <polars.DataFrame>, "Table1b": <polars.DataFrame>}
```

Reading Parquet with the pandas backend additionally requires `pyarrow` or
`fastparquet`; polars reads Parquet natively with no extra dependency.

## Single-table export

```python
# Standard (Citus)
handle = ie.export_file(
    dataset_id=93953,
    table_schema_id="68dd41f0...",
    mime_type="xlsx",   # "csv" or "xlsx"
)
xlsx_bytes = handle.result()

# BigData variant
handle = ie.export_file_dl(
    dataset_id=93953,
    table_schema_id="68dd41f0...",
)
```

## Whole-dataset export

```python
# All tables in one file (CSV, XLSX or ZIP of CSVs)
handle = ie.export_dataset_file(dataset_id=93953, mime_type="zip")
zip_bytes = handle.result()

# BigData variant
handle = ie.export_dataset_file_dl(dataset_id=93953)
```

## Choosing the right export method

| Situation | Method |
|-----------|--------|
| Standard (Citus) dataset, all tables | `etl_export()` |
| BigData dataset, all tables | `etl_export()` (v4/v5) |
| One table, CSV/XLSX (Citus) | `export_file()` |
| One table, BigData | `export_file_dl()` |
| Whole dataset, user-facing format | `export_dataset_file()` |
