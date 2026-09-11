# For custodians

A custodian builds and administers a dataflow: designs the tables and fields,
writes the quality rules, and manages the shared code lists. This page covers
what the library gives you for that work.

Everything here needs a **custodian key** — one generated from the custodian view
of the dataflow. Check with `flow.capabilities().role`.

## See the whole dataflow

A custodian key reads the dataflow unscoped, which a reporter key cannot:

```python
flow = reportnet.ReportnetClient(api_key=key).for_dataflow(2003)
contents = flow.get_dataflow_contents()

print(contents.info.name)
print(len(contents.reporting_datasets), "reporting datasets")
print(len(contents.reference_datasets), "reference datasets")
```

One call returns every kind of dataset in the dataflow — reporting, reference,
test, design, data collections and EU datasets — so prefer it over several
separate lookups.

## Design datasets, and what QC rule ids mean

Quality-control rules address data as `dataset_<id>."table"`. That `<id>` is
always a **design dataset** — never a reporting, reference or data-collection id.

```python
for d in flow.get_design_datasets():
    print(f"dataset_{d.id}", d.name)
```

```
dataset_108946 Descriptive data
dataset_108944 Spatial data
dataset_108942 Descriptive reference data
```

So a rule reading `dataset_108946."agglomerations"` is written against the
*Descriptive data* schema. At validation time Reportnet resolves that to
whichever copy of the schema is in scope — France's dataset when validating
France, Italy's when validating Italy.

The link is `schema_id`, shared by every copy of a schema:

```python
by_schema = {d.schema_id: d for d in contents.design_datasets}
for r in contents.reporting_datasets:
    print(by_schema[r.schema_id].name, "->", r.name, r.id)
```

```
Descriptive data -> France 108952
Descriptive data -> Italy 108953
```

**You need this lookup to read or write QC rules.** A schema export does not
contain it — the ids appear only inside the rule SQL — and design ids change
between dataflows, so no rule is portable without remapping them.

## Reference data and code lists

See [reference datasets](reference-datasets.md). The short version: they are
locked by default, and `import_frames` unlocks, uploads and re-locks for you.

## Job history

Every import, export and validation in the dataflow, newest first:

```python
for job in flow.list_jobs(dataset_id=108952, job_type="VALIDATION"):
    print(job.id, job.status, job.status_changed_at, job.info or "")
```

Useful for two things: finding out *why* someone's import failed — `job.info`
carries Reportnet's own message — and knowing which run a set of validation
results belongs to, since the results themselves carry no timestamp.

## Deleting data

```python
flow.delete_dataset_data(dataset_id=108960)                       # whole dataset
flow.delete_table_data(dataset_id=108960, table_schema_id="...")  # one table
```

No undo. Check what is there first.

## What a custodian key cannot do

| | |
|---|---|
| Read and export any dataset | ✅ |
| Import to a reference or test dataset | ✅ once unlocked |
| Lock and unlock reference datasets | ✅ |
| Import to a **reporter's** dataset | ❌ |
| Import to the data collection | ❌ |

A reporter's data can only be uploaded with that reporter's own key. There is no
unlock for it — that is a permission boundary, not a lock. If you also report for
a country, generate a second key from that country's reporter view; the same
person holding both roles still needs two keys.

## Releasing

There is no release endpoint, for custodians either. Releasing and creating the
data collection are done on the Reportnet website.
