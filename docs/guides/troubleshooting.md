# When something goes wrong

## "Forbidden" / 403

Almost always the key's **role**, not a missing permission.

- Uploading report data needs a **reporter** key. A custodian key cannot do it,
  even for someone who is also a reporter. See
  [getting started](getting-started.md#the-one-thing-that-confuses-everybody).
- A reporter key must be scoped to a country: use `find_reporter("FR")`.
- A reporter key cannot read the dataflow without that scope, and a custodian
  key cannot read it *with* one. The library handles this, but it explains why a
  key that works for one call fails on another.

Check what you have:

```python
print(flow.capabilities().role)
```

## The upload said OK but nothing arrived

An upload returns success when the job is *accepted*, not when it has run. If
you did not call `.wait()`, you only started it.

`import_frames` always waits. `import_file` does not — add `.wait()`.

Then confirm:

```python
print(me.verify_import(dataset_id=108952))
```

## "Import files contain incorrect headers"

Your columns do not exactly match the table's fields. Let `import_frames` fix it
(it does by default), or compare them yourself:

```python
table = me.get_schema(dataset_id=108952).table("Agglomerations")
print(set(table.column_names()) ^ set(my_frame.columns))
```

## "Import is not allowed for this dataset"

The dataset is locked. Reference datasets are locked by default and must be
unlocked before they accept data — `import_frames` does that for you and locks
them again afterwards. If you are uploading to a *reporting* dataset and see
this, check you have the right dataset id.

## Validation results look wrong, or unchanged

You are probably reading an older run. Check `result.is_stale`, and see
[checking your data](validation.md#make-sure-you-are-reading-this-run).

## Validation seems stuck

It is slow — twenty minutes is normal on a big dataflow. Do not submit another;
Reportnet refuses it and shows an error on your dataflow. Poll instead:

```python
result = me.get_validation_results(dataset_id=108952)
```

## Seeing what the library is doing

```python
import logging
logging.basicConfig(level=logging.INFO)
```

You get one line per job with its status and how long it took, plus warnings
about anything changed on your behalf. Use `DEBUG` to see every request.

Nothing is ever logged that would expose your API key.

## Errors you may see

| Error | Means |
|---|---|
| `AuthError` | key rejected, or wrong role for this call |
| `JobFailedError` | the job ran and failed — read `.info` for Reportnet's reason |
| `JobTimeoutError` | still running; read results instead of retrying |
| `DatasetLockedError` | another job is using the dataset; wait |
| `DiscoveryNotPermittedError` | this key cannot list datasets — take the id from the website |

All of them inherit from `ReportnetError`, so you can catch the lot:

```python
try:
    me.import_frames(dataset_id=108952, frames=frames)
except reportnet.ReportnetError as exc:
    print("Upload failed:", exc)
```
