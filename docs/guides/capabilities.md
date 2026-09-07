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
| Export reference, EU and data-collection datasets | no | yes |
| Resolve code lists | no | yes |
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

Resolving code lists requires exporting the shared reference dataset, which
reporter keys cannot do. Columns constrained to a code list are therefore typed
as strings rather than enumerations, and `get_template()` issues a warning.
Values are still checked during validation.

## Verifying an upload

A `FINISHED` job does not confirm that rows were stored. Import statistics are
readable by both roles:

```python
me.verify_import(dataset_id=DATASET_ID)["Contacts"]
# {'records': 1, 'last_import': datetime(...), 'file_extension': 'csv'}
```

This is one request. A full export returns the stored rows but runs
asynchronously and takes longer.
