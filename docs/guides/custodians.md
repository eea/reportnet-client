# For custodians

A custodian builds and administers a dataflow: designs the tables and fields,
writes the quality rules, and manages the shared code lists. This page covers
what the library gives you for that work.

Everything here needs a **custodian key** — one generated from the custodian view
of the dataflow. Check with `flow.capabilities().role`. The one exception is
[designing schemas](#designing-schemas), which needs your **login token**
instead of a key.

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

## Reading the quality rules

If the dataflow is **public**, its whole design — including every QC rule and
its SQL — is downloadable with no API key at all:

```python
import reportnet

schema = reportnet.get_public_schema(1748)
print(len(schema.rules), "rules,", len(schema.sql_rules()), "with SQL")

for rule in schema.sql_rules():
    print(rule.shortcode, rule.severity, rule.dataset_ids)
```

```
815 rules, 176 with SQL
ReportPeriod-4 WARNING (98701,)
UWWTPs-31 ERROR (98701, 98699)
```

`rule.dataset_ids` are the **design** dataset ids in the rule's SQL — pair them
with `get_design_datasets()` to see which dataset each one means. 35 of those
rules read more than one dataset, and those are the ones you cannot understand
without that mapping.

Needs the `schema` extra (`pip install "reportnet-client[schema]"`), or pass
`parse=False` to just keep the spreadsheet.

**This is the only way to read rule SQL with an API key.** The `/rules/`
endpoints refuse an API key of any role, custodian included — measured, not
assumed. A [login token](#get-a-login-token) can read them
(`GET /rules/{schemaId}/dataflow/{dataflowId}`, tested on the sandbox in
November 2026). The public download only works for published dataflows: a
private one, including a private test copy of a public dataflow, raises
`DataflowNotPublicError`.

Writing rules is still web-UI only. `createNewRule` and `updateRule` exist in
Reportnet's source but are not reachable with an API key.

## Designing schemas

You can build a dataset schema from Python: create a design dataset, then add,
change, move and delete its tables and fields. This only works while the
dataflow is being designed.

### Get a login token

An API key **cannot** change a schema: Reportnet answers 403. You need the
token the web app uses while you are logged in.

1. Log in to Reportnet in your browser.
2. Open the developer tools (F12) → **Application** → **Session storage** →
   the Reportnet site → `reportnet_03`.
3. Copy `accessToken` and `refreshToken`.

```python
import reportnet

client = reportnet.ReportnetClient.from_tokens(
    access_token="eyJ...", refresh_token="eyJ...", sandbox=True)
```

Treat both tokens like a password. The client renews the access token itself.
The refresh token changes each time it does so, so if you save it for later,
save `client.tokens.refresh_token` at the end, not the one you started with.

### Build a schema

```python
flow = client.for_dataflow(11468)
ds = flow.create_design_dataset("Sites and measurements")
designer = flow.design(ds.id)

sites = designer.add_table("Sites", mandatory=True)
code = designer.add_field(sites, "SiteCode", "TEXT", pk=True, required=True)
designer.add_field(sites, "Status", "CODELIST", codelist=["open", "closed"])

measurements = designer.add_table("Measurements")
designer.add_field(measurements, "Site", "LINK", required=True, link_to=code)

designer.update_field(code, description="National site code")
designer.move_field(code, position=0)
print(designer.export_table_definition("Sites"))   # CSV, as in the web app
```

Every method reads the schema back after the change and returns what Reportnet
now holds. If that differs from what you asked for, it raises
`SchemaReadbackError`.

### What the designer refuses, and why

| It refuses | Because | To override |
|---|---|---|
| A client made with an API key | Reportnet answers 403 | use `from_tokens` |
| A dataset that is not a design dataset | schemas are changed on design datasets only | — |
| A schema that already has a data collection or reporting datasets | the change would reach reporters; not tested | `flow.design(id, allow_after_data_collection=True)` |
| Changing a table that holds records | the web app locks such tables, but the API does not | `force=True` |
| A table or field name already in use | the API accepts duplicates; the web app does not | — |

Deleting a table or field has no undo.

**If a change fails with a server error, read the schema before you try
again.** On the sandbox, a field update answered "500" and was saved anyway.
`SchemaWriteUncertainError` says so in its message.

Not yet possible from Python: deleting a whole design dataset, importing a
table definition, copying schemas between dataflows, and the dataset's
"reference dataset" and "public" settings. Use the web app for these.

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
| Change a schema | ❌ needs a [login token](#get-a-login-token) |

A reporter's data can only be uploaded with that reporter's own key. There is no
unlock for it — that is a permission boundary, not a lock. If you also report for
a country, generate a second key from that country's reporter view; the same
person holding both roles still needs two keys.

## Releasing

There is no release endpoint, for custodians either. Releasing and creating the
data collection are done on the Reportnet website.
