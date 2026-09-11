# Reference datasets

**Reporters can skip this page.** Reference datasets hold the code lists a
dataflow shares with everyone. You only ever read them, and
[`get_template()`](schema.md#code-lists) does that for you.

The rest is for custodians, who are the only ones who can change them.

## See what is there

```python
for ref in flow.get_reference_datasets():
    print(ref.id, ref.name, "unlocked" if ref.updatable else "locked")
```

## Change one

They are **locked** by default, and the lock is checked when the upload job
runs — not when you send it. So an upload to a locked dataset is accepted, and
then fails with *"Import is not allowed for this dataset."*

`import_frames` handles it: unlock, upload, lock again — and it restores the
lock even if the upload fails.

```python
flow.import_frames(dataset_id=108960, frames={"Agglomerations": df}, replace=True)
```

Re-locking is also what rebuilds the dataset's public files, so don't skip it if
you do this by hand:

```python
flow.set_reference_dataset_updatable(dataset_id=108960, updatable=True)
# ... upload ...
flow.set_reference_dataset_updatable(dataset_id=108960, updatable=False)
```

## What a custodian key can do

Measured against a live dataflow:

| | |
|---|---|
| Read and export any dataset | ✅ |
| Import to a reference or test dataset | ✅ once unlocked |
| Import to a **reporter's** dataset | ❌ |
| Import to the data collection | ❌ |

A reporter's data can only be uploaded with that reporter's own key. There is no
unlock for it — that is a permission boundary, not a lock.
