# Downloading

## Your data as tables

```python
export = me.export_frames(dataset_id=108952)

for name, df in export.frames.items():
    print(name, len(df), "rows")
```

`export.frames` is a dict of table name to DataFrame. `export.verification`
tells you whether what came back matched the dataset's structure.

You get one DataFrame per table, in pandas or polars. Useful for checking what
is actually stored, or for pulling last year's submission as a starting point
for this year's.

## As a file

```python
handle = me.etl_export(dataset_id=108952)
data = handle.result()                 # waits, then returns the bytes
open("export.zip", "wb").write(data)
```

## Data with geometry

If your dataset holds shapes or points, ask for a GeoDataFrame:

```python
import reportnet

export = me.export_frames(dataset_id=108957)
gdf = reportnet.to_geodataframe(export.frames["ProtectedArea"])
```

Needs the `spatial` extra (`pip install "reportnet-client[spatial]"`).

## Export formats

Reportnet has more than one export format and they are not interchangeable. The
library picks the right one for your dataflow automatically. You only need to
care if you are told to use a specific version:

```python
me.etl_export(dataset_id=108952, version=5)     # zipped Parquet
```

Version 5 is not a drop-in replacement for version 4 — it can return a different
set of tables and a different geometry encoding. Use the default unless you have
a reason.

## Next

[When something goes wrong](troubleshooting.md).
