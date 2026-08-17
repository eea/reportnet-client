# API notes

Findings about the Reportnet 3 API itself — what it can't do, where its own
documentation is wrong or incomplete, and which endpoints exist but aren't
wrapped yet.

This page exists because most of this library's value is hard-won knowledge
about a partly-undocumented API. Negative results are worth as much as code:
without them, the next person re-derives them.

*Last verified: 17 August 2026, against production.*

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
the API serves. Several endpoints this library depends on — and which the help
pages document — are missing from it entirely:

| Endpoint | In Swagger? | In help docs? | Works? |
|---|---|---|---|
| `POST /dataset/exportFile` | No | Yes | Yes |
| `POST /dataset/exportFileDL` | No | Yes | Yes |
| `GET /dataset/exportDatasetFile` | No | Yes | Yes |
| `GET /dataset/exportDatasetFileDL` | No | Yes | Yes |
| `PUT /orchestrator/jobs/addValidationJob/{datasetId}` | No | Yes | Yes |
| `GET /orchestrator/jobs/pollForJobStatus/{jobId}` | No | Yes | Yes |
| `GET /validation/listGroupValidations{,DL}/{datasetId}` | No | Yes | Yes |
| `GET /downloadValidation/{snapshotId}` | No | Yes | Yes |
| `PUT /referenceDataset/{datasetId}` | No | No | Yes |

**Practical consequence:** treat Swagger as a lower bound on the API, and the
help pages as a separate, partly-overlapping source. Neither is complete on its
own. Never conclude "the endpoint doesn't exist" from Swagger alone.

## `/private/` routes are not reachable with an API key

Roughly 17 of the dataset service's routes and several elsewhere sit under
`/private/`. These are internal service-to-service calls and return 404 for
API-key authentication regardless of your permissions.

The clearest example: `GET /dataflow/private/v1/{dataflowId}/isBigDataflow`
looks purpose-built for detecting BigData dataflows, and is in the Swagger spec,
but 404s for API-key auth. That's why
[`is_big_dataflow()`][reportnet.ReportnetClient.is_big_dataflow] reads the
`bigData` field from `GET /dataflow/v1/{dataflowId}` instead.

## Two confirmed `providerId` traps

Both discovered by live testing, both encoded in the client:

- **v4/v5 `etlExport` and `importFileData` reject `providerId` outright (403)**
  for reporter-level keys — even when the value correctly matches the dataset's
  own owner. `datasetId` already identifies the provider. This is why
  `DataflowClient` deliberately does *not* auto-fill `provider_id` on those
  calls for BigData dataflows.
- **v3 (Citus) `etlExport` uses `dataProviderCodes`** (an ISO country code)
  rather than `providerId`. Filled in automatically when the client came from
  `find_reporter()`.

## Response quirks

- `PUT /orchestrator/jobs/addValidationJob/{datasetId}` returns a **bare integer**
  job ID, not the `{"jobId": ..., "pollingUrl": ...}` object other async
  operations return. The client synthesises the polling URL.
- Auth failures are sometimes wrapped as **HTTP 500** by the gateway, with
  `UNAUTHORIZED` or `401` in the body. The client detects this and raises
  `AuthError` rather than retrying.
- `numberOfRecords` in validation results arrives as a **string**, not a number.

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
