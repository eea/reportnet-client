# Permissions

Reportnet assigns permissions per API key role. No endpoint reports the role
directly, so the library determines it by probing. The result is cached for the
lifetime of the client.

```python
caps = flow.capabilities()
print(caps.summary())
# "dataflow 1234: reporter key; cannot discover dataset IDs"
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
| List dataset identifiers | no | yes |
| Export reference, EU and data-collection datasets | no | yes |
| Resolve code lists | no | yes |
| Read release history | no | yes |

Permissions are defined per endpoint and dataset type. The tables published in
the API's own operation descriptions are reproduced in
[API notes](../api-notes.md).

## Dataset identifiers

Enumerating datasets requires administrator permissions. Reporter keys must
take dataset identifiers from the dataset URL in the web interface.

Calls that require enumeration raise
[`DiscoveryNotPermittedError`][reportnet.DiscoveryNotPermittedError], a
subclass of `AuthError`. Operations that accept a dataset identifier directly
are unaffected.

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
