# Interactive Notebooks

Three [marimo](https://marimo.io) notebooks are included for hands-on exploration.
Each opens in your browser and connects to the Reportnet API using a key stored in
your system keychain.

All notebooks have a **Sandbox** checkbox to connect to `sandbox.reportnet.europa.eu`
instead of production — useful for testing without affecting live data.

## Run locally

```bash
uv sync --group explore
uv run marimo edit notebooks/01_explore_dataflow.py
```

For the spatial notebook also install geopandas:

```bash
pip install "reportnet-client[spatial]"
uv run marimo edit notebooks/03_spatial_geodataframe.py
```

## Static previews

The links below are non-interactive snapshots exported on the last push to `main`.
They show the notebook layout and documentation but cannot make live API calls.

| Notebook | Preview | Purpose |
|---|---|---|
| 01 — Explore a Dataflow | [open](notebooks/01_explore_dataflow.html) | Browse reporters, inspect schemas, visualise the dataflow structure, download empty templates |
| 02 — Import / Export Pipeline | [open](notebooks/02_import_export_pipeline.html) | End-to-end import → validate → export workflow |
| 03 — Spatial GeoDataFrame | [open](notebooks/03_spatial_geodataframe.html) | Export spatial datasets and convert to a geopandas GeoDataFrame |
