# What your key can do

Reportnet grants permissions per **key role**, and there is no endpoint that
reports which role a key has. The library probes for it — two cheap requests,
cached for the client's lifetime.

```python
caps = flow.capabilities()
print(caps.summary())
# "dataflow 2003: reporter key; cannot discover dataset IDs"
```

::: reportnet.Capabilities

## Why this matters

The role doesn't only change *what succeeds* — it changes how requests must be
**built**. Verified live on dataflow 2003:

| Key role | `importFileData` on BigData |
|---|---|
| Custodian | `providerId` **present** → 403 |
| Reporter | `providerId` **absent** → 403 |

The library handles this for you: it infers the role, and `import_file()`
retries once with the opposite choice if the inference was wrong. You should
never need to pass `provider_id` yourself.

## What each role can do

Measured on a BigData dataflow:

| | Reporter | Custodian |
|---|---|---|
| Read dataset schemas | ✅ | ✅ |
| Import data | ✅ | ✅ |
| Validate, read results | ✅ | ✅ |
| Check import status | ✅ | ✅ |
| Delete own table data | ✅ | ✅ |
| List dataset IDs | ❌ | ✅ |
| Confirm an import landed (`verify_import`) | ✅ | ✅ |
| Detect backend (`is_big_dataflow`) | ✅ | ✅ |
| Export your own reporting dataset | ✅ | ✅ |
| Export reference / EU / data-collection datasets | ❌ | ✅ |
| Resolve codelists | ❌ | ✅ |
| Release history | ❌ | ✅ |

## Two consequences for Reporters

**You cannot list your dataset IDs.** Only `GET /dataflow/v1/{id}` lists them,
and reporter keys are forbidden from it. Take the ID from the web UI — it's in
the URL when you open the dataset. Anything needing only a dataset ID
(`get_schema`, `import_file`, `validate`) works normally.

Calls that need discovery raise
[`DiscoveryNotPermittedError`][reportnet.DiscoveryNotPermittedError] — a
subclass of `AuthError` carrying an actionable message rather than a bare 403.

**You can read your own data back, but not the shared reference datasets.**
Exporting your reporting dataset works; the code lists it links to do not.
That is why code-list columns come back as plain strings.

For a quick check after an upload, prefer
[`verify_import()`][reportnet.DataflowClient.verify_import] over a full export
— it is one request rather than a multi-minute job:

```python
it.verify_import(dataset_id=108953)["Reporter"]
# {'records': 1, 'last_import': datetime(...), 'file_extension': 'csv'}
```

This matters because [a FINISHED job is not evidence data
landed](../api-notes.md). Inspecting the rows themselves still has to happen in
the web UI.
