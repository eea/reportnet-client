# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python client library for the [EEA Reportnet 3 REST API](https://help.reportnet.europa.eu/rest-api/).
Base URL: `https://api.reportnet.europa.eu`. Auth is a static `Authorization: ApiKey {key}` header — no OAuth.

## Commands

```bash
# Install all dev dependencies (creates .venv automatically)
uv sync

# Run all tests
uv run pytest

# Docs (live preview at http://127.0.0.1:8000)
uv run mkdocs serve

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
  __init__.py       # public re-exports only
  client.py         # ReportnetClient — one method per API operation
  dataflow.py       # DataflowClient — pre-fills dataflow_id / provider_id
  _http.py          # httpx.Client wrapper: auth header, error mapping, retry/back-off
  models.py         # JobHandle, JobStatus enum
  exceptions.py     # ReportnetError hierarchy
  providers.py      # DataProvider mapping table + by_id / by_country / by_group helpers
  keychain.py       # system keychain helpers (save_key / get_key / delete_key)
  _util.py          # DataFrame → in-memory CSV, mime-type helpers
tests/
  conftest.py                  # shared respx mock router + client fixtures
  test_imports.py / test_exports.py / test_validations.py / test_jobs.py
  test_providers.py / test_dataflow_client.py / test_http_retry.py
```

### Key design decisions

**`JobHandle`** is returned by all async operations. It holds `job_id`, `polling_url`, `_provider_id` (injected into poll requests for reporters), and a back-reference to the HTTP session. Methods:
- `.status()` — single poll
- `.wait(poll_interval, timeout, on_status)` — blocks until terminal; raises `JobFailedError` on non-FINISHED terminal statuses; calls `on_status(JobStatus)` each poll if provided
- `.result(...)` — `.wait()` + download; only valid on export handles (`_is_export=True`)

**`_http.py`** wraps `httpx.Client`. Maps 401/403 → `AuthError`, 429 → `RateLimitError`, other non-2xx → `APIError`. Retries `TransportError` for all methods (max 3, exponential back-off); retries 5xx for GET only (POST/PUT may have side effects).

**`DataflowClient`** (via `client.for_dataflow(dataflow_id, provider_id=...)`) pre-fills `dataflow_id` and uses the stored `provider_id` as a default for every call. All methods accept a per-call `provider_id` override.

**Sync-only**. The library is synchronous (`httpx` sync). Async support is a future concern; don't add it speculatively.

**DataFrames are optional**. `_util.py` uses narwhals to support polars, pandas, modin, etc. `import_file` accepts `str | Path | bytes | IO[bytes] | DataFrame`; DataFrames are serialized to CSV in-memory.

### API endpoint map

| Method | Endpoint | Notes |
|--------|----------|-------|
| `import_file` | `POST /dataset/v2/importFileData/{datasetId}` | multipart/form-data |
| `etl_import` | `POST /dataset/v1/{datasetId}/etlImport` | JSON; Citus datasets only |
| `etl_export` | `GET /dataset/v{version}/etlExport/{datasetId}` | async; ZIP of CSVs; version=4 (default) or 5 |
| `export_file` | `POST /dataset/exportFile` | async; single-table CSV/XLSX |
| `export_file_dl` | `POST /dataset/exportFileDL` | async; single-table BigData variant |
| `export_dataset_file` | `GET /dataset/exportDatasetFile` | async; whole-dataset CSV/XLSX/ZIP |
| `export_dataset_file_dl` | `GET /dataset/exportDatasetFileDL` | async; whole-dataset datalake variant |
| `add_validation_job` | `PUT /orchestrator/jobs/addValidationJob/{datasetId}` | |
| `list_group_validations` | `GET /validation/listGroupValidations/{datasetId}` | Citus |
| `list_group_validations_dl` | `GET /validation/listGroupValidationsDL/{datasetId}` | BigData |
| `download_validation_snapshot` | `GET /downloadValidation/{snapshotId}` | returns CSV bytes |
| `set_reference_dataset_updatable` | `PUT /referenceDataset/{datasetId}` | |
| *(internal)* polling | `GET /orchestrator/jobs/pollForJobStatus/{jobId}` | used by `JobHandle` |

### etlExport download URL

The poll response for a FINISHED export job includes `{"status": "FINISHED", "downloadUrl": "/orchestrator/jobs/downloadEtlExportedFile/{jobId}?..."}`. `JobHandle._poll()` captures this automatically; `result()` then GETs it.

### Exception hierarchy

```
ReportnetError
  APIError(status_code, response_body)
    AuthError          # 401 / 403
    RateLimitError     # 429
  JobFailedError(job_id, status)   # terminal but not FINISHED
  JobTimeoutError(job_id)          # wait() exceeded timeout
```

### Testing

All tests use `respx` to mock `httpx` — no live HTTP calls. `conftest.py` provides a `mock_client` fixture that yields a `(ReportnetClient, respx.MockRouter)` pair. Tests assert both the outbound request shape and the returned `JobHandle` / bytes / dict.
