# Export data

All export methods return a [`JobHandle`][reportnet.JobHandle]. The job runs
in the background; call `.result()` for raw bytes or `.to_frames()` to get
DataFrames directly.

## ETL export — ZIP of CSVs (recommended)

Returns a ZIP archive with one CSV per table.

```python
ie = client.for_dataflow(1619).for_provider(17)

handle = ie.etl_export(dataset_id=93953)
zip_bytes = handle.result(poll_interval=10.0, timeout=600.0)

with open("export.zip", "wb") as f:
    f.write(zip_bytes)
```

## Export directly to DataFrames

Requires `pip install "reportnet-client[dataframe]"`.

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

## Checked export — `export_frames()`

`etl_export().to_frames()` returns whatever the server sent. `export_frames()`
downloads once and checks it against a freshly fetched schema, so a truncated
or wrong-shaped payload is caught rather than silently analysed:

```python
result = ie.export_frames(dataset_id=93953, timeout=600)
print(result.verification.summary())
frames = result.frames
```

It raises `ExportVerificationError` when tables or columns do not match. Pass
`strict=False` to warn and log instead — every frame is still returned
alongside the report, so nothing is discarded:

```python
result = ie.export_frames(dataset_id=93953, strict=False)
if not result.verification.ok:
    print(result.verification.missing_tables, result.verification.unexpected_tables)
```

The check is **structural**: it proves the table and column names match the
schema, never that the values are right or complete. Empty tables are reported
in `verification.empty_tables` rather than treated as a failure — on dataflow
2003 a reference export returned all seven expected tables, all empty, and a v5
export returned [47 tables for a seven-table
schema](../live-tests-2003.md#reference-export-accepted-does-not-mean-useful).
Both are exactly what this check exists to surface.

Pass `table_schema_id=` to export and verify a single table.

## ETL export v5 — Parquet

Use `version=5` to receive partitioned Parquet files instead of CSVs.
It is opt-in only and never chosen automatically. Size and speed depend on
the dataset; see the [live comparison](../live-tests-2003.md). Production v5
adds `data_provider_code`, and its ZIP layout differs from v4. On reference
108961 it returned 47 tables for a seven-table schema; avoid v5 reference
exports on this dataflow. The reporting spatial dataset passed an explicit
content comparison.
`to_frames()` handles it transparently, same as v4:

```python
frames = ie.etl_export(dataset_id=93953, version=5).to_frames(poll_interval=10.0, timeout=600.0)
# {"Table1a": <polars.DataFrame>, "Table1b": <polars.DataFrame>}
```

Reading Parquet with the pandas backend additionally requires `pyarrow` or
`fastparquet`; polars reads Parquet natively with no extra dependency.

## Legacy exports: production limitations

On dataflow 2003, both keys returned 403 for `export_file()` and
`export_file_dl()`, and 404 for both `export_dataset_file` variants
(8 September 2026). Custodian access did not fix them. Prefer `etl_export()`;
pass `table_schema_id` to request one table. The examples below describe the
wrapped routes, not verified alternatives on this deployment.

### Single-table export

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

### Whole-dataset export

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
| One table, BigData | `etl_export(table_schema_id=...)` |
