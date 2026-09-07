# API notes

Findings about the Reportnet 3 API itself — what it can't do, where its own
documentation is wrong or incomplete, and which endpoints exist but aren't
wrapped yet.

This page exists because most of this library's value is hard-won knowledge
about a partly-undocumented API. Negative results are worth as much as code:
without them, the next person re-derives them.

*Last verified: 17 August 2026, against production (dataflows 1619 / 2003).
The endpoint behaviour below comes from a full `pytest --integration` run:
58 passed, 4 xfailed.*

## There is no "release" endpoint

**You cannot submit/release a dataset through the API.** Releasing is a
web-UI-only action.

The library can import, validate, export and delete data, and can *read* the
release history — but nothing creates a release. This is an API limitation, not
a gap in the client.

Checked across every documented surface:

| Source | Release-creating operation? |
|---|---|
| All 13 Swagger service specs (~115 paths) | No |
| [Import API endpoints](https://help.reportnet.europa.eu/import-api-endpoints/) | No |
| [Export API endpoints](https://help.reportnet.europa.eu/export-api-endpoints/) | No |
| [Validation API endpoints](https://help.reportnet.europa.eu/validation-api-endpoints/) | No |

Everything release-adjacent that *does* exist is read-only or administrative:

| Endpoint | What it does | Wrapped? |
|---|---|---|
| `GET /snapshot/v1/historicReleases` | List past releases | [`list_historic_releases()`][reportnet.ReportnetClient.list_historic_releases] |
| `GET /snapshot/downloadHistoricReleases/{datasetId}` | Release history as CSV | Not yet |
| `POST /snapshot/exportHistoricReleases/{datasetId}` | Kick off that CSV export | Not yet |
| `GET /dataset/getReleasedDatasetDataInfo` | Info about released data | Not yet |
| `GET`/`POST`/`PUT`/`DELETE /release-receipts` | Release *receipts*, not releases | Not yet |
| `DELETE /snapshot/v1/{idSnapshot}/dataset/{idDataset}/delete` | Delete a snapshot | Not yet |

So a fully automated pipeline can prepare and validate a submission, but a human
still has to press **Release** in the Reportnet UI.

!!! note "How certain is this?"
    Strong, but not absolute. Swagger alone would not be enough — it is
    provably incomplete (see below). The confidence comes from the operation
    being absent from *both* the Swagger specs of all 13 services *and* all
    three help-documentation categories. If Reportnet adds one, re-run the
    check at the bottom of this page.

## The Swagger spec is incomplete

`https://api.reportnet.europa.eu/swagger-ui.html` does **not** list everything
the API serves. Endpoints this library uses successfully, and which the help
pages document, are missing from it entirely.

The live column below comes from the `--integration` suite against production
dataflow 1619 (see `tests/test_integration.py`):

| Endpoint | In Swagger? | In help docs? | Live result |
|---|---|---|---|
| `PUT /orchestrator/jobs/addValidationJob/{datasetId}` | No | Yes | **Works** |
| `GET /orchestrator/jobs/pollForJobStatus/{jobId}` | No | Yes | **Works** |
| `GET /validation/listGroupValidationsDL/{datasetId}` | No | Yes | **Works** |
| `GET /dataset/v4/etlExport/{datasetId}` | Yes | Yes | **Works** |
| `POST /dataset/exportFile` | No | Yes | 403 — needs extra permissions |
| `GET /dataset/exportDatasetFile` | No | Yes | **404** |
| `GET /dataset/exportDatasetFileDL` | No | Yes | **404** |
| `GET /snapshot/v1/historicReleases` | Yes | — | 403 — needs custodian access |

Two separate lessons here, and it's worth not conflating them:

1. **Swagger genuinely under-reports.** The orchestrator and validation
   endpoints in the top rows are absent from every spec yet work in production
   and are exercised by the test suite. So you can never conclude "this
   endpoint doesn't exist" from Swagger alone.

2. **But absence from Swagger is still a useful smell.** The three endpoints
   that 404 or 403 in practice are *also* the ones missing from Swagger. For
   `exportDatasetFile` / `exportDatasetFileDL` the most likely reading is that
   they are documented in the help pages but **not deployed** on this
   environment — Swagger is right and the help pages are stale. The
   corresponding client methods (`export_dataset_file`,
   `export_dataset_file_dl`) therefore may not be usable in production; their
   integration tests are marked `xfail`.

**Practical consequence:** treat Swagger and the help pages as two partial,
partly-contradictory sources. When they disagree, only a live call settles it —
which is what the `--integration` suite is for.

## Endpoints that need more than a reporter API key

Confirmed live. These are wrapped by the client and are correct, but your key
may not be permitted to call them:

| Endpoint | Client method | Result |
|---|---|---|
| `POST /dataset/exportFile` | `export_file()` | 403 — needs additional permissions |
| `GET /snapshot/v1/historicReleases` | `list_historic_releases()` | 403 — needs custodian access |

A 403 here means the key lacks the right, not that the call is malformed — the
client raises `AuthError` either way, so check your key's role before assuming
a bug.

## `/private/` routes are not reachable with an API key

Roughly 17 of the dataset service's routes and several elsewhere sit under
`/private/`. These are internal service-to-service calls and return 404 for
API-key authentication regardless of your permissions.

The clearest example: `GET /dataflow/private/v1/{dataflowId}/isBigDataflow`
looks purpose-built for detecting BigData dataflows, and is in the Swagger spec,
but 404s for API-key auth. That's why
[`is_big_dataflow()`][reportnet.ReportnetClient.is_big_dataflow] reads the
`bigData` field from `GET /dataflow/v1/{dataflowId}` instead.

## `providerId` on BigData depends on the key's ROLE, not the backend

This was previously recorded here as "BigData rejects `providerId`". That is
only half true, and the missing half makes imports impossible for the role most
likely to be doing them. Both directions are confirmed live on dataflow 2003:

| Key role | `importFileData`, `etlExport` **and** `GET /dataflow/v1/{id}` |
|---|---|
| Custodian-level | `providerId` **present** → 403 (writes/exports) |
| Reporter | `providerId` **absent** → 403 |

The same parameter governs all three operations. It was missed three times
because each was investigated separately; `providerId` is the single thing a
reporter-scoped key needs on every one of them.

Isolated on `etlExport` for a reporter key, v3 and v4 alike:

| Parameters sent | Result |
|---|---|
| `providerId` (with or without `dataProviderCodes`) | **200** |
| `dataProviderCodes` only | 403 |
| neither | 403 |

So `dataProviderCodes` is a *filter*, not an authorisation — only `providerId`
grants the call.

A Reporter key for IT (provider 64) was refused without `providerId` and
accepted with it — job 248505 ran to FINISHED.

**There is no endpoint that reports a key's role.** The usable proxy is whether
the key may read `GET /dataflow/v1/{id}`: custodian-level keys can, and
reporter-scoped keys are 403'd. `DataflowClient._pid_bigdata_safe` uses exactly
that signal, and `import_file` retries once with the opposite choice if the
inference was wrong — safe, because a 403 means nothing was written.

- **v3 (Citus) `etlExport` uses `dataProviderCodes`** (an ISO country code)
  rather than `providerId`. Filled in automatically when the client came from
  `find_reporter()`.

## What a Reporter key can and cannot do

Measured on dataflow 2003 (BigData) with a Reporter key for IT:

| Capability | Result |
|---|---|
| `GET /dataschema/v1/datasetId/{id}` (own + reference datasets) | ✅ |
| `GET /dataschema/v1/dataset/{id}/exportFieldSchemas` (schema as ZIP) | ✅ |
| `GET /dataset/checkImportProcess/{id}` | ✅ |
| `GET /dataset/getImportRelatedStatistics/{id}` — row counts per table | ✅ |
| `GET /dataset/getAvailableForManualEditingTables/{id}` | ✅ |
| `GET /representative/v1/dataflow/{id}` | ✅ |
| `GET /dataflow/v1/{id}/getmetabase` — name, status, `bigData` | ✅ |
| `GET /dataflow/v1/dataflowName/{id}` | ✅ |
| `POST /dataset/v2/importFileData/{id}` **with** `providerId` | ✅ |
| `PUT /orchestrator/jobs/addValidationJob/{id}` + `listGroupValidationsDL` | ✅ |
| `DELETE /dataset/v1/{id}/deleteTableData/{tableSchemaId}` | ✅ |
| `GET /dataflow/v1/{id}` **without** `providerId` | ❌ 403 |
| `GET /dataflow/v1/{id}?providerId=<own>` | ✅ own reporting datasets + reference datasets |
| `GET /dataflow/v1/{id}?providerId=<another provider>` | ❌ 403 |
| `GET /dataset/v{3,4,5}/etlExport/{id}` on its **own reporting dataset**, **with** `providerId` | ✅ |
| The same export **without** `providerId` | ❌ 403 |
| Exporting **reference / EU / data-collection / test** datasets | ❌ 403 (role table forbids it) |
| `exportFile`, `exportFileDL` | ❌ 403 |
| `etlImport`, v1 `importFileData`, `generateImportPresignedUrl` | ❌ 403 |
| `getSimpleSchema`, `getTableSchemasIds`, `list-imported-files`, `preparations` | ❌ 403 |
| `snapshot/v1/historicReleases`, `document/v1/dataflow/{id}`, `weblink/v1/dataflow/{id}` | ❌ 403 |

That list is exhaustive for reads: every public `GET` in the Swagger specs
taking only a dataflow or dataset id was probed.

Two consequences worth designing around:

1. **A reporter discovers its own dataset IDs by sending `providerId`.**
   The unscoped read is 403; the scoped read returns that provider's reporting
   datasets and the dataflow's reference datasets, with names and statuses.
   Another provider's id is refused, so the scoping is enforced rather than
   advisory.
2. **A reporter *can* export its own reporting dataset** — provided
   `providerId` is sent. It cannot export reference, EU, data-collection or
   test datasets; the role tables (below) forbid those.

   Independently, `GET /dataset/getImportRelatedStatistics/{id}` gives per-table
   `{"lastImportDate", "numberOfRecordsImported", "fileExtension"}`. Since a
   FINISHED job is *not* evidence that data landed, that is the cheap check
   after an upload — wrapped as
   [`verify_import()`][reportnet.DataflowClient.verify_import] — while a full
   export is the expensive one.

## Response quirks

- `PUT /orchestrator/jobs/addValidationJob/{datasetId}` returns a **bare integer**
  job ID, not the `{"jobId": ..., "pollingUrl": ...}` object other async
  operations return. The client synthesises the polling URL.
- Auth failures are sometimes wrapped as **HTTP 500** by the gateway, with
  `UNAUTHORIZED`, `401` **or `403`** in the body. The client detects this and
  raises `AuthError` rather than retrying. The 403 form looks like this — note
  the real status is only visible inside `message`:

  ```json
  {"status": 500, "error": "Internal Server Error",
   "message": "status 403 reading JobControllerZuul#addImportJob(...)",
   "path": "/dataset/v2/importFileData/108953"}
  ```

- `numberOfRecords` in validation results arrives as a **string**, not a number.

## `etlImport` silently discards records without `countryCode`

Every record in an `etlImport` body **must** carry `countryCode`:

```json
{"tables": [{"tableName": "T",
             "records": [{"countryCode": "IT", "fields": [...]}]}]}
```

Omit it and the request is accepted, a job is created, and that job reaches
**`FINISHED`** — having imported **nothing**. There is no error, no warning and
no partial result; the only way to detect it is to re-export and count rows.

`ReportnetClient.etl_import` warns when any record lacks the field, but the
deeper lesson generalises: **on this API a `FINISHED` job is not evidence that
data landed.** Verify writes by reading them back.

Two further limits found while loading a real payload
(dataflow 1570 → 2003, September 2026):

- The documented `etlImport` payload ceiling is 220 MB, but an **85 MB** body
  failed with `HTTP 500 COMMAND_EXCEPTION`. Chunk large imports, or prefer
  `importFileData`, whose CSV encoding is far more compact than JSON-wrapped
  GeoJSON.
- `etlImport` is **Citus-only**. On a BigData dataflow `importFileData` is the
  only wrapped write path — `etlImportDL` exists but is not wrapped yet.

## A reporter-scoped key may not read `/dataflow/v1/{id}`

Keys differ in scope in a way that cuts across the client's layering. One key
tested on dataflow 2003 could read `/representative/v1/dataflow/{id}` and
`/dataschema/v1/datasetId/{id}` but got **403 on `/dataflow/v1/{id}`**.

That single endpoint backs `get_dataflow`, `get_reporting_datasets`,
`is_big_dataflow`, `dataset()`, `ping()` and — indirectly — `import_file`,
which consults `is_big_dataflow()` to decide whether to send `providerId`.
Before this was handled, importing with such a key failed at the preflight and
reported a 403 against `/dataflow/v1/{id}`, *not* the endpoint being called —
badly misleading when debugging.

`DataflowClient` now degrades instead: when the backend cannot be read it omits
`providerId` (whose *presence* is what BigData rejects) and `validate()` tries
the DL listing endpoint before falling back to the Citus one.

## Endpoints that exist but aren't wrapped yet

Candidates for future work, all confirmed present in the Swagger specs:

| Endpoint | Why it might be worth adding |
|---|---|
| `GET /dataset/{datasetId}/generateImportPresignedUrl` | Presigned upload — would sidestep buffering large files through the client |
| `POST /dataset/{datasetId}/etlImportDL` | BigData counterpart to `etlImport`, which is Citus-only today |
| `GET /dataschema/v1/getTableSchemasIds/{datasetId}` | Table schema IDs without fetching the full schema |
| `GET /dataschema/v1/getSimpleSchema/dataset/{datasetId}` | Lighter-weight schema |
| `GET`/`PUT`/`DELETE /dataset/v1/{datasetId}/field/{fieldId}/attachment` | Attachment fields are unsupported by the client today |
| `GET /dataset/getImportRelatedStatistics/{datasetId}` | Richer import feedback than `checkImportProcess` |
| `GET /dataset/list-imported-files`, `GET /dataset/download-imported-file` | Retrieve what was previously uploaded |
| `GET /dataflow/v1/dataflowName/{dataflowId}` | Cheap name lookup vs. the full dataflow payload |

## Re-running these checks

The Swagger UI is a JavaScript shell; fetch the underlying specs directly.
`GET /swagger-resources` lists every service:

```bash
# List all service specs
curl -s https://api.reportnet.europa.eu/swagger-resources | python3 -m json.tool

# Download them all
for s in dataset collaboration communication dataflow document indexSearch \
         inspireHarvester rod recordstore validation ums orchestrator; do
  curl -s -o "$s.json" "https://api.reportnet.europa.eu/$s/v2/api-docs"
done

# Search every operation for a keyword (e.g. release)
python3 - <<'PY'
import json, glob, re
for f in sorted(glob.glob("*.json")):
    spec = json.load(open(f))
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            blob = f"{path} {op.get('summary','')} {op.get('operationId','')}".lower()
            if re.search(r"releas|snapshot|submit", blob):
                print(f"[{f[:-5]:<12}] {method.upper():<6} {path}")
PY
```

No API key is needed — the spec endpoints are public.


## Swagger descriptions carry authoritative role tables

Each operation's `description` field lists the roles allowed **per dataset
type**. This is the closest thing to an authoritative permission model the API
publishes, and it is not visible in the endpoint list — only in the operation
detail. For example `GET /dataset/v4/etlExport/{datasetId}`:

| Dataset type | Allowed roles |
|---|---|
| Reporting | CUSTODIAN, STEWARD, OBSERVER, REPORTER WRITE, REPORTER READ, LEAD REPORTER, STEWARD SUPPORT |
| Test | CUSTODIAN, STEWARD, STEWARD SUPPORT |
| Reference | CUSTODIAN, STEWARD, OBSERVER, STEWARD SUPPORT |
| Design | CUSTODIAN, STEWARD, EDITOR WRITE, EDITOR READ |
| EU | CUSTODIAN, STEWARD, OBSERVER, STEWARD SUPPORT |
| Data collection | CUSTODIAN, STEWARD, OBSERVER, STEWARD SUPPORT |

That table explains observed behaviour exactly: a reporter can export its own
*reporting* dataset but not a *reference* one. `importFileData` has its own
table (Reporting: LEAD REPORTER, REPORTER WRITE, NATIONAL COORDINATOR).

**Read these before concluding a role cannot do something.** Extract them with:

```bash
curl -s https://api.reportnet.europa.eu/dataset/v2/api-docs | python3 -c "
import json,sys
spec=json.load(sys.stdin)
for m,op in spec['paths']['/dataset/v4/etlExport/{datasetId}'].items():
    print(op.get('description',''))"
```
