# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python client library for the [EEA Reportnet 3 REST API](https://help.reportnet.europa.eu/rest-api/).
Base URL: `https://api.reportnet.europa.eu`. Auth is a static `Authorization: ApiKey {key}` header — no OAuth.

## Commands

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_imports.py

# Run a single test by name
pytest tests/test_imports.py::test_import_file_csv

# Lint + type-check
ruff check src tests
mypy src
```

## Architecture

### Layout

```
src/reportnet/
  __init__.py       # public re-exports only
  client.py         # ReportnetClient — one method per API operation
  _http.py          # httpx.Client wrapper: injects auth header, raises APIError on non-2xx
  models.py         # JobHandle, JobStatus enum, typed dataclasses
  exceptions.py     # ReportnetError hierarchy
  _util.py          # DataFrame → in-memory CSV, mime-type helpers
tests/
  conftest.py       # shared respx mock router fixture
  test_imports.py / test_exports.py / test_validations.py / test_jobs.py
```

### Key design decisions

**`JobHandle`** is returned by all async operations (`import_file`, `etl_import`, `etl_export`, `add_validation_job`). It holds `job_id`, `polling_url` (used verbatim from the API response), and a back-reference to the client. Methods:
- `.status()` — single poll
- `.wait(poll_interval, timeout)` — blocks until terminal; raises `JobFailedError` on non-FINISHED terminal statuses
- `.result(...)` — `.wait()` + download, only valid on export handles

**`_http.py`** wraps `httpx.Client`. Every response goes through a single error-checking helper that maps 401/403 → `AuthError`, other non-2xx → `APIError`. The client is passed into `JobHandle` so polling reuses the same session/auth.

**Sync-only**. The library is synchronous (`httpx` sync). Async support is a future concern; don't add it speculatively.

**pandas is optional**. `_util.py` attempts `import pandas` at call time and raises `ImportError` with an install hint if missing. `importFileData` accepts `str | Path | bytes | IO[bytes] | pd.DataFrame`; DataFrames are serialized to CSV in-memory via `io.BytesIO`.

### API endpoint map

| Method | Endpoint | Notes |
|--------|----------|-------|
| `import_file` | `POST /dataset/v2/importFileData/{datasetId}` | multipart/form-data |
| `etl_import` | `POST /dataset/v1/{datasetId}/etlImport` | JSON; Citus datasets only |
| `etl_export` | `GET /dataset/v4/etlExport/{datasetId}` | async; result is ZIP of CSVs |
| `export_file` | `POST /dataset/exportFile` | sync; returns raw bytes |
| `export_file_dl` | `POST /dataset/exportFileDL` | sync; BigData variant |
| `add_validation_job` | `PUT /orchestrator/jobs/addValidationJob/{datasetId}` | |
| `list_group_validations` | `GET /validation/listGroupValidations/{datasetId}` | Citus |
| `list_group_validations_dl` | `GET /validation/listGroupValidationsDL/{datasetId}` | BigData |
| `set_reference_dataset_updatable` | `PUT /referenceDataset/{datasetId}` | |
| *(internal)* polling | `GET /orchestrator/jobs/pollForJobStatus/{jobId}` | used by `JobHandle` |

### Open question: etlExport download URL

The v4 export response only documents `{"pollingUrl": "...", "status": "..."}`. After the job reaches `FINISHED`, the download URL is not documented. The current plan is to derive it from `jobId` (e.g. `/orchestrator/jobs/download/{jobId}`) — verify against the live API and update `models.py` / `client.py` if different.

### Exception hierarchy

```
ReportnetError
  APIError(status_code, response_body)
    AuthError          # 401 / 403
  JobFailedError(job_id, status)   # terminal but not FINISHED
  JobTimeoutError(job_id)          # wait() exceeded timeout
```

### Testing

All tests use `respx` to mock `httpx` — no live HTTP calls. `conftest.py` provides a `mock_client` fixture that yields a `(ReportnetClient, respx.MockRouter)` pair. Tests assert both the outbound request shape and the returned `JobHandle` / bytes / dict.
