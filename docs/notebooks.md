# Interactive Notebooks

A [marimo](https://marimo.io) notebook is included for hands-on work. It opens in
your browser and talks to the live Reportnet API using a key you paste in — every
cell that would change something sits behind a button, so you can read the whole
thing without a key and without touching a dataflow.

## Run locally

```bash
uv sync --group explore
uv run marimo edit notebooks/01_reporter_workflow.py
```

## 01 — Reporter workflow

Upload a report and validate it, as the French reporter on dataflow 2003
(*UWWTD — TESTING — BIG DATA*), using the **Toulon subset** in
`notebooks/data/toulon/` — 15 agglomerations and 15 treatment plants around
Toulon, taken from France's 2022 submission.

Five steps: connect → find the dataset → load the data → upload → validate.

It is built around the three things that actually go wrong, rather than a happy
path:

- **Your key carries a role, not an identity.** A custodian key cannot upload
  report data even if the same person is also a lead reporter. `providerId` is
  required for one role and refused for the other.
- **Reportnet wants headers that exactly match the schema.** A real extract never
  arrives that way. Get it wrong and the request returns HTTP 200 and the *job*
  fails — `import_frames` reshapes the data for you.
- **Validation results can be stale and look identical to fresh ones.** The
  endpoint carries no timestamp or run id, so check `result.is_stale`.

A spatial notebook covering `ProtectedArea` geometries is planned; the extracted
geometries already live in `notebooks/data/toulon/spatial/`.

## Static preview

The link below is a non-interactive snapshot exported on the last push to `main`.
It shows the layout and the explanation but cannot make live API calls.

| Notebook | Preview |
|---|---|
| 01 — Reporter workflow | [open](notebooks/01_reporter_workflow.html) |
