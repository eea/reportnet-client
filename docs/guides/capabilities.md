# Permissions

Reportnet assigns permissions per API key role. No endpoint reports the role
directly, so the library determines it by probing. The result is cached for the
lifetime of the client.

```python
caps = flow.capabilities()
print(caps.summary())
# "dataflow 1234: reporter key; reads must be provider-scoped"
```

::: reportnet.Capabilities

## Effect on request construction

The role determines how requests are built, not only which succeed. Both
directions are confirmed against a BigData dataflow:

| Key role | `importFileData` and `etlExport` |
|---|---|
| Custodian | `providerId` present: HTTP 403 |
| Reporter | `providerId` absent: HTTP 403 |

The library selects the correct value and retries once with the alternative if
the request is refused. `provider_id` does not need to be passed explicitly.

## Operations by role

| Operation | Reporter | Custodian |
|---|---|---|
| Read dataset schemas | yes | yes |
| Upload data | yes | yes |
| Verify an upload | yes | yes |
| Validate and read results | yes | yes |
| Resolve country code to provider | yes | yes |
| Export own reporting dataset | yes | yes |
| List own dataset identifiers | yes | yes |
| List all reporters' datasets | no | yes |
| Request reference export 108961 on flow 2003 | accepted; empty v4 and mismatched v5 contents | v5 accepted; contents need verification |
| Export EU and data-collection datasets | previously refused; not retested in September audit | role table permits; not retested |
| Resolve code lists | depends on reference access and coverage | depends on reference access and coverage |
| Read release history | no | yes |

Permissions are defined per endpoint and dataset type. The tables published in
the API's own operation descriptions are reproduced in
[API notes](../api-notes.md).

## Dataset identifiers

Reading the dataflow requires `providerId` for reporter keys. With it, the
response contains that provider's own reporting datasets and the dataflow's
reference datasets. Requesting another provider's identifier returns HTTP 403.

The client sends it automatically when provider-scoped, so `dataset()`,
`datasets_by_table()` and `reference_dataset()` work for both roles:

```python
me = flow.find_reporter("IT")
me.datasets_by_table()
```

An unscoped client with a reporter key raises
[`DiscoveryNotPermittedError`][reportnet.DiscoveryNotPermittedError], a
subclass of `AuthError`, naming the methods that scope it. Only custodian keys
can read the dataflow unscoped and see every reporter's datasets.

## Code lists

Resolving code lists requires exporting the shared reference dataset. The Italy
reporter successfully exported reference 108961 with provider scope in the
[September audit](../live-tests-2003.md); do not reject this operation solely
because the key is reporter-scoped. However, v4 returned empty tables and v5 returned
extra tables outside the schema; neither resolved its ten linked fields.
Access and usable contents may differ for other references.
If export or resolution fails, `get_template()` warns; `strict=True` raises
instead of returning unconstrained LINK columns.

## What this key has actually been observed to do

`capabilities()` *infers* how to scope requests. `permission_evidence()` reports
what this client has actually observed, with no probing and no new requests:

```python
for observation in flow.permission_evidence():
    print(observation.operation, observation.request_accepted,
          observation.payload_verified, observation.detail)
```

Each `OperationEvidence` keeps three facts apart, and `None` always means
"not checked" — never "permitted":

| Field | Answers |
|---|---|
| `request_accepted` | Did the API accept the request? |
| `payload_verified` | Did the returned payload match the schema? |
| `workflow_verified` | Did an upload survive a full readback comparison? |

An accepted request is not a verified payload — the dataflow 2003 audit found a
v5 reference export that returned HTTP 200 and 40 tables that were not in the
requested schema. Entries are per exact request scope (key, dataset, version,
provider, filters) and are the latest observation, not an audit log or a
promise about the next call.

## Verifying an upload

A `FINISHED` job does not confirm that rows were stored. Import statistics are
readable by both roles:

```python
me.verify_import(dataset_id=DATASET_ID)["Contacts"]
# {'records': 1, 'last_import': datetime(...), 'file_extension': 'csv'}
```

This is one request. A full export returns the stored rows but runs
asynchronously and takes longer.
