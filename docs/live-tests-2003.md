# Live tests: BigData dataflow 2003

Verified on **8 September 2026**, production `api.reportnet.europa.eu`, dataflow
**UWWTD - TESTING - BIG DATA**. Used the supplied custodian key and the previously
stored Italy reporter key (provider 64). Keys were not added to source files or
overwritten in the keychain. Tests read metadata, validation results and exports;
no reporting data or shared QC rules were changed. Validation execution and
import/write permissions were not retested in this audit.
[Machine-readable measurements](assets/live-tests-2003.json) contain statuses,
timings and dimensions, without credentials or reporting rows.

## Permission findings

| Operation | Italy reporter | Custodian |
|---|---|---|
| Unscoped dataflow discovery | 403 | 200; four reporting datasets |
| Discovery with `providerId=64` | 200; two own datasets, four references | 403 |
| Discovery with `providerId=17` | 403 | 403 |
| Reporting dataset schemas | 200 | 200 |
| v5 reporting export 108953, correct provider scope | FINISHED + download | FINISHED + download |
| v5 reference export 108961, correct provider scope | FINISHED + download; wrong table set (see below) | FINISHED + download; same ZIP byte count |
| Import statistics and import status | 200 | 200 |
| Existing BigData validation results | 200 | 200 |
| Release history, dataset 108953 | 403 | 200, empty list |
| `exportFile` and `exportFileDL` | 403 | 403 |
| `exportDatasetFile` and `exportDatasetFileDL` | 404 | 404 |
| Private `isBigDataflow` route | 404 | 404 |
| QC rule listing, with/without provider scope | 403 | 403 |
| QC history on design dataset 108946 | 403 | 403 |
| QC CSV export request | 403 | 403 |
| SQL rule evaluation (`SELECT 1`, design dataset 108946) | 403 | 403 |

**Reference export is not universally forbidden to reporters.** The Italy
reporter completed and downloaded reference 108961 (v5, job 249257); the
custodian did too (job 249258), both 14,189,962 bytes. Both v4/v5 Swagger
descriptions omit reporters from reference roles, so the published role table
does not fully predict live scoped authorization. This does not establish
access to all reference, EU, collection or test datasets, or establish that
the downloaded payload is the requested dataset.

Reporter discovery and reporting-data export are real capabilities. Older
claims that reporters cannot do either are incorrect. Custodian release-history
access works, but does not fix the legacy export or QC-rule routes. A 403 alone
does not establish whether the cause is role authorization, API-key restrictions
or gateway policy. Source code presence is not proof of deploy-time access.

`capabilities()` remains a request-scoping inference, not a complete operation
permission matrix. Separate reporter/custodian clients and provider scope are
covered in the [workflow guide](guides/workflows.md).

## v4 versus v5: measured results

Two sequential runs of each version on each dataset, in order **4, 5, 5, 4**.
Job time includes submission, queueing and processing, observed by polling every
two seconds. It is not isolated server CPU time. MB below means decimal MB.

| Dataset | Version | ZIP size | Job time, two runs | Download, two runs | Local parsing median |
|---|---|---:|---|---|---:|
| Descriptive 108953: 15 empty tables | v4 | 5,143 bytes | 27.4 / 62.6 s | 0.07 / 0.07 s | 0.0003 s |
| Descriptive 108953: 15 empty tables | v5 | 17,521 bytes | 56.7 / 58.5 s | 0.10 / 0.11 s | 0.0015 s |
| Spatial 108958: 989 ProtectedArea records | v4 | 70.61 MB | 77.3 / 60.7 s | 1.79 / 1.55 s | 0.625 s |
| Spatial 108958: 989 ProtectedArea records | v5 | 136.23 MB | 48.2 / 52.6 s | 2.81 / 2.97 s | 0.626 s |

Local parse medians were remeasured from the downloaded archives with the
corrected parser, five iterations per archive. They include ZIP decompression
and DataFrame construction, but exclude geometry decoding. Job IDs for these
eight runs: **249248–249255**. The empty dataset is useful for format testing,
not throughput estimation. Two runs cannot establish a general speed guarantee.

**Keep v4 as the BigData default.** V5's spatial jobs were faster in this sample,
but its transfer was 1.93 times larger and its local parsing speed was the same.
On empty tables it had more overhead. V5 can be useful when binary geometry and
Parquet are desired; benchmark the actual workload before choosing it. This
sample does not establish performance for large non-spatial tables.

## Format and correctness findings

Production v5 is a partitioned ZIP:

```text
ProtectedArea/
  ProtectedArea_<UUID>/
    0_0_0.parquet
```

The old parser keyed files by their leaf name. On the descriptive dataset,
**15 tables collapsed into one `0_0_0` entry**, silently overwriting earlier
tables. The fix groups by table directory and concatenates partitions, while
retaining support for flat Parquet archives. Synthetic regression tests cover
repeated partition names, multiple partitions, an outer folder and empty tables;
the corrected parser also recovered all tables from both downloaded archives.

V5 is not identical to v4:

- It includes `data_provider_code`: 31 spatial columns versus 30 in v4.
- V5 geometry is EWKB binary. In this dataset, v4 contained GeoJSON Feature
  strings, despite the older blanket claim that v4 always exports WKT.
- The EWKB geometry SRID is **4258**. Use
  `to_geodataframe(frame, "geometry_polygon", crs="EPSG:4258")`. The helper now
  supports WKB and handles RN3's zero-length bytes as missing geometry. Its
  default CRS is retained for compatibility; passing a CRS assigns it and does
  not reproject coordinates.
- Empty CSV fields parsed as nulls where Parquet retained empty strings.
  V5 business fields in this sample were strings; it did not automatically
  produce numeric/date types for every schema field.

After sorting by `record_id`, all **989 unique IDs** and all non-geometry values
matched after normalizing null/empty strings. All **75 line geometries** and
**914 polygon geometries** matched exactly after decoding GeoJSON and EWKB.
The real v5 archive also converted to a GeoDataFrame with 914 non-null polygons.

The descriptive dataset exported zero rows even though its last-import
statistics recorded an earlier imported row. Those statistics describe a past
import, not current contents; do not use them as a current row-count guarantee.

## Reference export: accepted does not mean useful

The reference follow-up used the corrected parser and compared the downloaded
contents with schema 108961, which defines **seven tables**:

| Reporter request (`providerId=64`) | Result |
|---|---|
| v4, job 249259 | Seven expected tables, all empty |
| v5, job 249260 | **47 tables**, including 40 outside the requested schema; the seven expected tables are empty |
| Resolve spatial reporting dataset's ten LINK fields from either export | **0/10 resolved** |

The v5 archive includes unrelated table names such as `dcpWFDwaterbodies` and
`Agglomerations`. It is not equivalent to the requested reference dataset.
This is a live payload mismatch, independent of the fixed filename parser bug.
Avoid v5 reference exports here, and check exported table names against the
requested schema. The reproducible benchmark script raises on this mismatch.
The reference v5 result must not be generalized from the successful spatial
reporting-data comparison above. No attempt was made to use extra tables as
replacement code lists or to infer access to other datasets from their presence.

Thus the old blanket **403** claim is false, but usable reporter code-list
resolution is still unavailable for this reference in the current dataflow
state. The existing warning/`strict=True` behavior remains essential. We did
not establish whether the empty code lists reflect missing source data or
provider filtering; custodian v4 contents would be a separate check.

## Quality-control rule authoring and transfer

The [official reporter help](https://help.reportnet.europa.eu/reportnet-3-1-reporter-howto/validate-data/quality-control/)
describes inspecting QC rules, custom SQL expressions and downloading a CSV
catalogue in the UI. That catalogue is distinct from validation results and
is not established as a round-trip import format.

The official source, inspected at commit
[`f7b5777feba131fbee0ad88298745adb0279ad3a`](https://github.com/eea/eea.reportnet3/tree/f7b5777feba131fbee0ad88298745adb0279ad3a),
contains these routes in
[`RulesController`](https://github.com/eea/eea.reportnet3/blob/f7b5777feba131fbee0ad88298745adb0279ad3a/common-interfaces/src/main/java/org/eea/interfaces/controller/validation/RulesController.java):

| Purpose | Route | Evidence from this audit |
|---|---|---|
| Read definitions | `GET /rules/{datasetSchemaId}/dataflow/{dataflowId}` | 403 both keys |
| Generate QC CSV | `POST /rules/exportQC/{datasetId}` | 403 both keys |
| Download generated CSV | `GET /rules/downloadQC/{datasetId}?fileName=...` | Not attempted; generation refused |
| Evaluate SQL | `POST /rules/evaluateSqlRule?datasetId=...` | 403 both keys |
| Create definition | `PUT /rules/createNewRule?datasetId=...` | Source only; mutation not attempted |
| Update definition | `PUT /rules/updateRule?datasetId=...` | Source only; mutation not attempted |

The [controller implementation](https://github.com/eea/eea.reportnet3/blob/f7b5777feba131fbee0ad88298745adb0279ad3a/validation-service/src/main/java/org/eea/validation/controller/RulesControllerImpl.java)
marks these operations hidden from Swagger and applies design-schema roles to
create/update/evaluate. It also shows that QC CSV generation returns no export
job handle, and download requires its generated filename. We have not confirmed
how to obtain that filename with API-key authentication. The only rules-schema
bulk import in this interface is a private service route, not evidence of a
supported public CSV upload API.

Consequently, use the web UI for authoring for now. A future library workflow
needs an established authorization path, a disposable design schema, definition
readback, and passing/failing test cases before enabling rule upload. Do not
advertise working API-key rule management from the source signatures alone.

## Reproduce the export benchmark

```bash
uv run python scripts/benchmark_exports.py 2003 108958 --output benchmark.json
# Reporter: add --provider-id 64. The script prompts securely for the key.
```

The script creates export jobs only, checks exported table names against the
schema, and records job/download/parse timings and dimensions without data rows
or credentials. Compare values separately: table/row counts alone do not prove
equivalence. The ordinary integration suite also includes uploads; do not run
it indiscriminately when intending a read-only audit.
