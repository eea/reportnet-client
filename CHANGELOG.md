# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the version is below `1.0.0`, breaking changes may land in a minor release;
they are always listed under **Changed** with a migration note.

## [Unreleased]

### Added

- **Schema design for custodians.** `DataflowClient.create_design_dataset()`
  and `DataflowClient.design()` return a `SchemaDesigner` that adds, changes,
  moves and deletes tables and fields, renames the dataset and sets its
  description, and exports a table definition as CSV. It reads the schema back
  after every change, and refuses API-key clients, non-design datasets,
  schemas that already have a data collection or reporting datasets, tables
  that hold records and duplicate names unless told otherwise. One `ReportnetClient` method per endpoint
  underneath (`create_table_schema()`, `update_field_schema()`, …).
- **Login-token authentication**, needed for schema design because API keys get
  403. `ReportnetClient.from_tokens()` renews the access token before it
  expires and once after a 401, and keeps the rotated refresh token
  (`client.tokens`, or an `on_refresh` callback).
  `ReportnetClient.from_credentials()` is experimental. Token and password
  query values are masked in the library's logs and in httpx's.
- `FieldSchema` gains `record_id`, `pk`, `read_only`, `max_size`,
  `codelist_items`, `valid_extensions`, `pk_referenced`, `raw` and
  `to_update_payload()`; `TableSchema` gains `record_id`, `not_empty`,
  `read_only`, `to_prefill`, `fixed_number`, `data_manually_editable` and
  `field()`; `DatasetSchema` gains `available_in_public` and
  `reference_dataset`. All have defaults, so existing code is unaffected.
- `Capabilities.auth_kind` (`"api_key"` or `"bearer"`).

### Fixed

- A login token that can no longer be renewed now raises `LoginTokenError`
  (a subclass of `AuthError`), and the message says to log in again.
  Before, `DataflowClient.get_dataflow_contents()` reported it as
  `DiscoveryNotPermittedError` with advice about scoping reporter keys, and
  `capabilities()` and `is_big_dataflow()` misread it as a key role. Reportnet
  answers an invalid refresh token with HTTP 500.
- `SANDBOX_URL` pointed at `https://sandbox.reportnet.europa.eu`, the sandbox
  *web app*, which answers API paths with an HTML page. It is now
  `https://sandbox-api.reportnet.europa.eu`. This also fixes
  `ReportnetClient.from_keyring(..., sandbox=True)` and
  `connect_interactive(..., sandbox=True)`.
- `TableSchema.from_dict()` raised `TypeError` on a table with no fields, which
  Reportnet returns as `"fieldSchema": null` rather than an empty list.

## [0.5.1] — 2026-08-17

### Fixed

- `get_template()` and `get_codelists()` raised `ColumnNotFoundError` when a
  reference dataset contained an empty table. Reportnet exports a zero-column
  CSV for a table with no rows, so the schema promises columns the export does
  not carry. Such fields are now reported as unresolved, consistent with every
  other unresolvable case.
- A LINK field whose codelist column exists but holds no values is also treated
  as unresolved. It would otherwise become `Enum([])`, which rejects every
  value — strictly worse than leaving the column a plain string.
- `zip_to_frames()` no longer fails on an export containing a zero-byte CSV
  member, so one empty table cannot sink an entire export. Applies to both the
  polars and pandas backends.

## [0.5.0] — 2026-08-17

First release with packaging metadata, so the first that is properly
installable and type-checkable by consumers.

### Added

- **PEP 561 support.** The package now ships `py.typed`, so `mypy` and
  `pyright` check calls against it. Previously its annotations were invisible
  downstream.
- **`LICENSE`** (EUPL-1.2), plus `readme`, `license`, `authors`, `keywords`,
  `[project.urls]` and Python-version classifiers in `pyproject.toml`.
- **`reportnet.__version__`.**
- **`DataflowContents` and `get_dataflow_contents()`** — `get_dataflow`,
  `get_reporting_datasets`, `get_reference_datasets`, `get_test_datasets` and
  `is_big_dataflow` all read the same `/dataflow/v1/{id}` endpoint; this fetches
  and parses it once.
- **Name-based lookup**: `dataset(table_name)`, `datasets_by_table()` and
  `reference_dataset(name)`, so datasets no longer have to be found by list
  position.
- **Logging.** The library logs to the `reportnet` logger with a `NullHandler`,
  staying silent until an application opts in. `DEBUG` for requests and job
  polls, `INFO` for job transitions and orchestration, `WARNING` for retries
  and any fallback that weakens a result. API keys are never logged.
- **`strict=` on `get_codelists()` and `get_template()`**, raising the new
  `CodelistResolutionError` instead of warning.
- **`docs/api-notes.md`** — API limitations and quirks, including the finding
  that no endpoint exists to release/submit a dataset.

### Changed

- **`ReportnetClient.etl_export()` now defaults to `version=None`** (auto-detect
  v3 vs v4) rather than `version=4`. Sending the wrong version mostly
  "succeeds" but returns a differently-shaped payload. Costs one cached
  `bigData` lookup; pass `version=` explicitly to skip it.
  *Migration:* callers relying on the old unconditional v4 default should pass
  `version=4` explicitly.
- **`get_template()` selects the reference dataset by schema coverage** instead
  of taking the first one. On dataflow 2003 the first reference dataset covers
  0 of 10 LINK fields while another covers all 10, so the old behaviour
  silently returned unconstrained string columns.
- **Codelist resolution never degrades silently.** Any path that leaves LINK
  columns unconstrained now warns and logs instead of passing quietly.
- **Module layout.** `JobHandle`/`JobStatus` moved to `reportnet.jobs`, the
  Mermaid renderer to `reportnet.viz`, and `connect_interactive` to
  `reportnet.interactive`. All names remain importable from `reportnet` and
  from their previous modules; no import should need changing.
- **Client layering is now explicit**: `ReportnetClient` owns endpoint quirks,
  `DataflowClient` owns scoping only.

### Fixed

- `to_mermaid()` issued three identical requests to `/dataflow/v1/{id}`; it now
  makes one.
- Error messages and docs told users to `pip install reportnet[...]`; the
  distribution is `reportnet-client`.
- `for_provider(42)` was documented as Ireland in a docstring, the README and
  four docs pages. 42 is Andorra; Ireland is 17.

### Documentation

- Rewrote `docs/index.md`, which contained a wrong install command, and
  reordered the guides to follow the reporting workflow.
- Documented that **releasing a dataset is not possible through the API** —
  verified against all 13 Swagger service specs and all three help-doc
  categories. A human must press *Release* in the Reportnet web UI.
- Recorded that `export_dataset_file` / `export_dataset_file_dl` return 404 on
  production and `export_file` / `list_historic_releases` require elevated
  rights.

### Continuous integration

- Tests now run on a Python 3.10–3.13 matrix, matching `requires-python`.

[Unreleased]: https://github.com/eea/reportnet-client/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/eea/reportnet-client/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/eea/reportnet-client/releases/tag/v0.5.0
