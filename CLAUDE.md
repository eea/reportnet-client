# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python client library for the [EEA Reportnet 3 REST API](https://help.reportnet.europa.eu/rest-api/).
Base URL: `https://api.reportnet.europa.eu` (sandbox: `https://sandbox.reportnet.europa.eu`,
VPN-only, separate keys). Auth is a static `Authorization: ApiKey {key}` header — no OAuth.

Licensed EUPL-1.2. The package is typed and ships `py.typed`.

## Commands

```bash
# Install all dev dependencies (creates .venv automatically)
uv sync

# Run all tests
uv run pytest

# Run live integration tests too (needs keyring credentials + network)
uv run pytest --integration

# Docs (live preview at http://127.0.0.1:8000)
uv run mkdocs serve

# Interactive exploration with marimo (installs explore group first)
uv sync --group explore
uv run marimo edit notebooks/01_explore_dataflow.py

# Run a single test file
uv run pytest tests/test_imports.py

# Run a single test by name
uv run pytest tests/test_imports.py::test_import_file_csv

# Lint + type-check
uv run ruff check src tests
uv run mypy src
```

## Architecture

### Layout

```
src/reportnet/
  __init__.py       # public re-exports + __version__ only
  client.py         # ReportnetClient — one method per API operation
  dataflow.py       # DataflowClient — pre-fills dataflow_id / provider_id
  jobs.py           # JobHandle, JobStatus — async job polling (holds an HTTP session)
  models.py         # frozen dataclasses parsed from API responses (no I/O)
  viz.py            # dataflow_to_mermaid — pure rendering, no I/O
  interactive.py    # connect_interactive — non-raising helper for notebooks/UIs
  _http.py          # httpx.Client wrapper: auth header, error mapping, retry/back-off
  _log.py           # NullHandler setup + get_logger(); see "Logging" below
  exceptions.py     # ReportnetError hierarchy
  providers.py      # DataProvider mapping table + by_id / by_country / by_group helpers
  keychain.py       # system keychain helpers (save_key / get_key / delete_key)
  _util.py          # DataFrame ↔ CSV/ZIP, schema → frame, codelists, geopandas
  py.typed          # PEP 561 marker — do not delete, downstream typing depends on it
tests/
  conftest.py                  # shared respx mock router + client fixtures
  test_imports.py / test_exports.py / test_validations.py / test_jobs.py
  test_dataflow.py / test_dataflow_client.py / test_schema.py
  test_providers.py / test_keychain.py / test_http_retry.py
  test_connect_interactive.py / test_notebooks.py
  test_packaging.py            # metadata, py.typed, back-compat re-exports
  test_reliability.py          # codelist coverage, logging, name-based lookup
  test_integration.py          # live API — skipped unless --integration
```

### The client layering rule

This is the load-bearing convention; keep new code on the right side of it.

* **`ReportnetClient`** owns every quirk that belongs to an *endpoint*: URL shape,
  parameter names, response oddities, and API version selection. Calling any
  method here directly is always correct.
* **`DataflowClient`** owns only *scoping*: which IDs get filled in when the
  caller omits them. It is obtained via `client.for_dataflow(dataflow_id, provider_id=...)`,
  and every method accepts a per-call `provider_id` override.

Endpoint knowledge therefore lives in exactly one place. When adding behaviour,
ask "is this about the endpoint, or about which IDs to send?" and put it
accordingly. The one deliberate exception is `DataflowClient._pid_bigdata_safe`,
which suppresses *auto-filled* `providerId` on BigData dataflows — auto-fill is
a scoping decision, so it belongs upstairs even though it consults an endpoint quirk.

### Key design decisions

**`DataflowContents`** — `get_dataflow`, `get_reporting_datasets`,
`get_reference_datasets`, `get_test_datasets` and `is_big_dataflow` all read the
*same* `/dataflow/v1/{id}` payload. Calling them individually costs one request
each; `get_dataflow_contents()` parses all of it from one. Use it whenever you
need more than one (`to_mermaid` does). `is_big_dataflow` is cached per
`ReportnetClient` — a dataflow never changes backend.

**`JobHandle`** is returned by all async operations. It holds `job_id`,
`polling_url`, `_provider_id` (injected into poll requests for reporters), and a
back-reference to the HTTP session. Methods:
- `.status()` — single poll
- `.wait(poll_interval, timeout, on_status)` — blocks until terminal; raises `JobFailedError` on non-FINISHED terminal statuses; calls `on_status(JobStatus)` each poll if provided
- `.result(...)` — `.wait()` + download; only valid on export handles (`_is_export=True`)
- `.to_frames(...)` — `.result()` + unzip into DataFrames (CSV/Parquet/JSON)

It lives in `jobs.py`, not `models.py`, because it performs network I/O.
`models.py` is parsed data only — `test_packaging.py` enforces that.

**Never degrade silently.** This is the rule that matters most in this domain:
unvalidated data doesn't fail at the user's desk, it fails as a rejected
submission weeks later. Any path that returns a *weaker* result than asked for
— unresolved codelists, a reference export that 403s, a guessed dataset — must
`warnings.warn` **and** log a warning, and must be escapable via `strict=True`
raising `CodelistResolutionError`. A bare `except ReportnetError: pass` is a bug.

`get_template()` picks its reference dataset by schema coverage
(`_best_reference_dataset`), never `refs[0]`. Verified live on dataflow 2003:
`refs[0]` covers 0 of 10 LINK fields there while `refs[2]` covers all 10, so the
old behaviour returned unconstrained string columns with no indication.
`build_codelists()` returns a `CodelistResolution` (values + resolved +
unresolved), not a bare dict, precisely so partial results are detectable.

**Logging** — the library logs to the `reportnet` hierarchy via
`_log.get_logger(__name__)` and installs a `NullHandler`, so it is silent unless
the application opts in. `DEBUG` = every request and poll; `INFO` = job
transitions and orchestration progress; `WARNING` = retries and every
degradation fallback. Never log headers — the API key lives there.

**Name-based lookup** — `dataset(table_name)`, `datasets_by_table()` and
`reference_dataset(name)` exist because real scripts were indexing by list
position (`ds[0]`, `refs[3]`). `dataset()` requires a provider-scoped client,
since table names repeat across reporters.

**Schema layer** — `get_schema()` returns a `DatasetSchema` of `TableSchema` /
`FieldSchema` / `FieldType`. `TableSchema` carries the DataFrame helpers:
`to_frame()` (empty typed template), `cast_frame()` (coerce an existing frame,
raising on bad Enum values), `validate_frame()` (returns a list of errors rather
than raising). `DataflowClient.get_template()` combines schema + codelist
resolution in one call; `get_codelists()` maps LINK fields to their valid values
by exporting the reference dataset.

**`ValidationResult`** — `DataflowClient.validate()` chains
`add_validation_job` → `wait` → `list_group_validations_dl` and parses the
result into `ValidationIssue` objects, with `.ok` / `.has_errors` /
`.has_blockers` / `.summary()` / `.to_frame()` and the untouched response in
`.raw`.

**`_http.py`** wraps `httpx.Client`. Maps 401/403 → `AuthError`, 423 →
`DatasetLockedError`, 429 → `RateLimitError`, other non-2xx → `APIError`. The
gateway sometimes wraps auth failures as HTTP 500; `_is_wrapped_auth_500()`
detects those and is used both to raise `AuthError` and to skip retries — keep
the two uses in sync. Retries `TransportError` for all methods (max 3,
exponential back-off); retries 5xx for GET only (POST/PUT may have side effects).

**Sync-only**. The library is synchronous (`httpx` sync). Async support is a
future concern; don't add it speculatively.

**DataFrames are optional**. `_util.py` uses narwhals to support polars, pandas,
modin, etc. `import_file` accepts `str | Path | bytes | IO[bytes] | DataFrame`,
plus DuckDB relations and GeoDataFrames; DataFrames are serialized to CSV
in-memory. Geometry round-trips as WKT (v4) or GeoJSON (v3) — `to_geodataframe()`
detects which. Optional deps are imported *inside functions* so `import reportnet`
never requires `keyring`, `polars` or `geopandas`; don't hoist those imports.

**Provider IDs.** Most countries appear twice in `providers.py` with different
IDs. Worked examples use **17 = Ireland (IE)**; 42 is Andorra, and was
mislabelled as Ireland throughout the docs before — `test_providers.py` pins this.

### API limitations worth knowing (see `docs/api-notes.md`)

**There is no release/submit endpoint.** Verified 2026-08-17 across all 13
Swagger service specs and all three help-doc categories. The library can
prepare and validate a submission; a human must press *Release* in the web UI.
Don't go looking for it again — and if you do find one, update
`docs/api-notes.md`.

**Swagger is incomplete.** `https://api.reportnet.europa.eu/swagger-ui.html`
omits endpoints this library uses successfully and that the help pages document
(`/dataset/exportFile`, `/orchestrator/jobs/*`, `/validation/listGroupValidations*`,
`/downloadValidation/*`, `/referenceDataset/*`). Never conclude an endpoint
doesn't exist from Swagger alone — check the help pages too. The specs are
public: `GET /swagger-resources` lists all 13 services, each at
`/{service}/v2/api-docs`.

**`/private/` routes 404 for API-key auth** — they're service-to-service. This
is why `is_big_dataflow` reads the `bigData` field rather than calling the
purpose-built `/dataflow/private/v1/{dataflowId}/isBigDataflow`.

`docs/api-notes.md` also lists endpoints that exist but aren't wrapped yet
(presigned upload, `etlImportDL`, attachment fields, lighter schema calls) —
check there before adding a method.

### API endpoint map

| Method | Endpoint | Notes |
|--------|----------|-------|
| `get_dataflow_contents` | `GET /dataflow/v1/{dataflowId}` | whole payload, one parse |
| `get_dataflow` / `get_reporting_datasets` / `get_reference_datasets` / `get_test_datasets` / `is_big_dataflow` / `ping` | `GET /dataflow/v1/{dataflowId}` | all the same endpoint |
| `get_reporters` | `GET /representative/v1/dataflow/{dataflowId}` | |
| `get_schema` | `GET /dataschema/v1/datasetId/{datasetId}` | |
| `import_file` | `POST /dataset/v2/importFileData/{datasetId}` | multipart/form-data |
| `etl_import` | `POST /dataset/v1/{datasetId}/etlImport` | JSON; Citus datasets only |
| `etl_export` | `GET /dataset/v{version}/etlExport/{datasetId}` | async; v3/v4 auto-selected, v5 opt-in |
| `export_file` | `POST /dataset/exportFile` | async; single-table CSV/XLSX |
| `export_file_dl` | `POST /dataset/exportFileDL` | async; single-table BigData variant |
| `export_dataset_file` | `GET /dataset/exportDatasetFile` | async; whole-dataset CSV/XLSX/ZIP |
| `export_dataset_file_dl` | `GET /dataset/exportDatasetFileDL` | async; whole-dataset datalake variant |
| `add_validation_job` | `PUT /orchestrator/jobs/addValidationJob/{datasetId}` | returns a bare int job ID |
| `list_group_validations` | `GET /validation/listGroupValidations/{datasetId}` | Citus |
| `list_group_validations_dl` | `GET /validation/listGroupValidationsDL/{datasetId}` | BigData |
| `download_validation_snapshot` | `GET /downloadValidation/{snapshotId}` | returns CSV bytes |
| `set_reference_dataset_updatable` | `PUT /referenceDataset/{datasetId}` | |
| `delete_dataset_data` | `DELETE /dataset/v1/{datasetId}/deleteDatasetData` | |
| `delete_table_data` | `DELETE /dataset/v1/{datasetId}/deleteTableData/{tableSchemaId}` | |
| `list_historic_releases` | `GET /snapshot/v1/historicReleases` | |
| `check_import_process` | `GET /dataset/checkImportProcess/{datasetId}` | lock/import status |
| *(internal)* polling | `GET /orchestrator/jobs/pollForJobStatus/{jobId}` | used by `JobHandle` |

### etlExport versions and the providerId trap

`etl_export(version=None)` (the default on both client layers) picks v4 for
BigData/DLT2 dataflows and v3 for Citus, via a cached `bigData` lookup. v5
(ZIP of Parquet) is never auto-selected — pass `version=5` explicitly. Sending
the wrong version mostly "succeeds" but returns a differently-shaped payload,
which is why guessing was replaced with a lookup.

Two confirmed-live API quirks, both encoded in the code with comments:

- **v4/v5 reject `providerId` outright (403)** for reporter-level keys, even when
  it correctly matches the dataset's owner. `dataset_id` already identifies the
  provider. Same for `importFileData` on BigData dataflows.
- **v3 (Citus)** uses `dataProviderCodes` (an ISO country code) instead, which is
  filled in automatically when the client came from `find_reporter()`.

### etlExport download URL

The poll response for a FINISHED export job includes
`{"status": "FINISHED", "downloadUrl": "/orchestrator/jobs/downloadEtlExportedFile/{jobId}?..."}`.
`JobHandle._poll()` captures this automatically; `result()` then GETs it.

### Exception hierarchy

```
ReportnetError
  APIError(status_code, response_body)
    AuthError            # 401 / 403, plus gateway-wrapped 401-as-500
    DatasetLockedError   # 423 — another job is already running on the dataset
    RateLimitError       # 429
  CodelistResolutionError(unresolved)  # only when strict=True
  JobFailedError(job_id, status)       # terminal but not FINISHED
  JobTimeoutError(job_id)              # wait() exceeded timeout
```

### Testing

All unit tests use `respx` to mock `httpx` — no live HTTP calls. `conftest.py`
provides `mock_router` and `client` fixtures. Tests assert both the outbound
request shape and the returned `JobHandle` / bytes / dict. Prefer asserting
`route.call_count` when a change is about *how many* requests are made.

`test_integration.py` hits the live API and is skipped unless `--integration` is
passed; it is not part of CI, so anything it covers also needs a unit test.

Known coverage gap: the pandas and geopandas fallback paths are skipped in CI
(only polars is installed), so the non-polars half of `_util.py` is unexercised.
