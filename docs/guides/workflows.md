# Reporter and custodian workflows

## Reporter: prepare, upload, check, release

Use the reporter's own provider scope. On BigData dataflow 2003 the Italy
reporter uses provider 64. A reporter can discover and export its own reporting
datasets. Reference access must be checked for the actual key and dataset;
the Italy reporter's spatial reference export was accepted but did not yield
usable code lists (see the [live audit](../live-tests-2003.md)).

```python
import reportnet

client = reportnet.ReportnetClient(api_key=reportnet.get_key(2003))
me = client.for_dataflow(2003).for_provider(64)
print(me.capabilities().summary())
print(me.datasets_by_table())
dataset = me.dataset("Spatial data")
schema = me.get_schema(dataset_id=dataset.id)
```

### One call: `prepare_submission()`

`prepare_submission()` runs the whole prepare-and-check cycle and refuses to
report success it has not verified. It preflights every table, exports a
baseline *before* writing anything, uploads, exports again, compares the two,
and only then runs RN3 validation.

```python
result = me.prepare_submission(
    dataset_id=dataset.id,
    frames=prepared_frames,          # {table_name: DataFrame}
    replace=False,                   # append; True replaces the uploaded tables
    codelists=known_values,          # optional; see "Code lists" below
    timeout=600,
)

print(result.readback.summary())
print(result.validation.summary())
if result.ready_for_review:
    print("Structure, readback and validation all clean — press Release in the web UI.")
else:
    print(result.validation.to_frame())
```

`SubmissionResult.ready_for_review` is true only when the export structure
matched, the readback matched **and** validation is clean. It is not a release:
[there is no release endpoint](../api-notes.md#there-is-no-release-endpoint),
so a human still presses **Release** in the RN3 web UI.

What the comparison actually guarantees:

- Rows are compared as **multisets**, so duplicates are preserved rather than
  collapsed, and tables you did not upload are checked for unexpected change.
- Values are normalised for transport only — empty CSV fields and nulls are
  treated alike, numbers are compared numerically, and geometry is compared as
  canonical WKB. There is no fuzzy tolerance and no reprojection: prepare data
  in the dataset's own CRS.
- Server-assigned `record_id` and `data_provider_code` are ignored.

What it does not do:

- It does not roll back. If the readback fails, earlier imports have already
  been written; `ReadbackVerificationError` says so, and validation is **not**
  started. Inspect the dataset before retrying — appending again duplicates rows.
- It does not replace RN3's own rules. Local `validate_frame()` checks cannot
  execute the server's custom SQL.

#### Code lists

If `codelists` does not cover a LINK or CODELIST field, the default warns and
logs, then relies on RN3 validation to catch bad values. Pass
`strict_codelists=True` to refuse instead — before anything is uploaded — when
a submission must not depend on server-side checks:

```python
# get_codelists() needs the reference dataset it should resolve against.
known_values = me.get_codelists(dataset_id=dataset.id, ref_dataset_id=REF_ID)
me.prepare_submission(dataset_id=dataset.id, frames=prepared_frames,
                      codelists=known_values, strict_codelists=True)
```

Code lists are not fetched automatically: `get_codelists()` runs a full
reference export job, which costs minutes and, [on dataflow
2003](../live-tests-2003.md#reference-export-accepted-does-not-mean-useful),
resolves none of the ten LINK fields. Obtain unresolvable lists from the
custodian.

### Step by step, when you need the intermediate results

The same cycle, run by hand — useful for inspecting each stage or for
sequencing uploads yourself:

1. Read the schema and prepare frames with its field names and types. Local
   `TableSchema.validate_frame()` checks are useful, but do not execute RN3's
   custom SQL rules. `get_template()` warns if code lists cannot be resolved;
   use `strict=True` when complete code lists are required.
2. Upload the prepared tables with `import_frames()`. Choose append versus
   replacement deliberately: append is the default, and rerunning an upload
   can duplicate records.
3. Read `verify_import()` for last-import statistics, then export and compare
   the current data with what you intended to upload. Import statistics are
   historical and do not prove the rows still exist.
4. Run `validate()`, inspect the issues, correct data, and repeat.
5. Review and press **Release** in the RN3 web UI.

```python
me.import_frames(
    dataset_id=dataset.id,
    frames=prepared_frames,
    replace=False,
    timeout=600,
)
print(me.verify_import(dataset_id=dataset.id))
actual = me.export_frames(dataset_id=dataset.id, timeout=600)   # schema-checked
# Compare actual.frames with prepared_frames, allowing for pre-existing rows on append.
result = me.validate(dataset_id=dataset.id, timeout=600)
print(result.summary())
if result.has_errors or result.has_blockers:
    print(result.to_frame())
```

## Custodian (admin): inspect and support reporters

Construct a separate client with the custodian key. Keep the reporter key in
its existing keychain entry; do not replace it merely to switch roles.

```python
import os

admin_client = reportnet.ReportnetClient(api_key=os.environ["REPORTNET_CUSTODIAN_KEY"])
admin = admin_client.for_dataflow(2003)
contents = admin.get_dataflow_contents()
for dataset in contents.reporting_datasets:
    print(dataset.id, dataset.provider_id, dataset.table_name)
references = admin.get_reference_datasets()
history = admin.list_historic_releases(dataset_id=108953)
```

Use name lookup and schema coverage to select reference data, distribute code
lists to reporters, inspect exports, and review validation results. A scoped
custodian client can select a reporter's datasets, while the library omits
`providerId` where custodian export authorization requires it.

`capabilities()` infers how to scope requests; it is not an exhaustive
permission check. Custodian access does not enable every API route. See the
[measured permissions and export comparison](../live-tests-2003.md).

## Custodian (admin): author quality-control rules

Rule definitions and validation results are different resources. The current
library runs existing RN3 rules and reads their results. It does not yet upload
or manage rule definitions.

The practical authoring workflow is currently through the RN3 web UI:

1. Work in the design dataset for the relevant schema. Define a custom QC rule
   with a stable short code, explanation, severity and SQL expression.
2. Check the SQL and test it with known passing and failing examples in a test
   dataset. Include missing values, boundary values and invalid code-list values.
3. Review the resulting issues and enable the rule when its behavior is correct.
4. Reporters can inspect **QC rules** and use **Download QCs** to obtain a CSV
   rule catalogue. Keep reviewed definitions and test cases under version control.

The [official reporter help](https://help.reportnet.europa.eu/reportnet-3-1-reporter-howto/validate-data/quality-control/)
explains automatic versus custom rules, SQL expressions and CSV download.
Do not assume that this CSV is a round-trip upload format.

The official server source exposes rule listing, create/update, SQL evaluation,
and QC export routes, but the read, evaluation and export probes returned 403
with **both** supplied roles on 8 September 2026. Rule creation/update was not
attempted: it would change the schema shared by reporting datasets. Therefore
API-key rule upload support remains unverified, rather than implemented or
proven impossible. The next step is to establish an RN3-supported authorization
path for these routes and a disposable design schema before adding a tested
rule create/update/download workflow to this library.
