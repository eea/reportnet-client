# Reference datasets (custodians)

Most reporters never need this page. Reference datasets hold the shared code
lists a dataflow uses, and only custodians can change them.

## Reading them

Anyone can read. If you just want the valid values for a field, use
`get_codelists()` instead — it picks the right reference dataset for you.

```python
for ref in flow.get_reference_datasets():
    print(ref.id, ref.name, "unlocked" if ref.updatable else "locked")
```

## Writing to them

A reference dataset is **locked** by default. An upload to a locked one is
accepted and then fails, because the lock is checked when the job runs rather
than when you send it.

`import_frames` handles the whole cycle — it unlocks, uploads, and locks again,
restoring the lock even if the upload fails:

```python
flow.import_frames(dataset_id=108960, frames={"Agglomerations": df}, replace=True)
```

Re-locking is also what regenerates the dataset's public files, so it is not an
optional tidy-up.

To do it by hand:

```python
flow.set_reference_dataset_updatable(dataset_id=108960, updatable=True)
# ... upload ...
flow.set_reference_dataset_updatable(dataset_id=108960, updatable=False)
```

## What custodian keys can and cannot do

Measured against a live dataflow:

| | Custodian key |
|---|---|
| Read any dataset in the dataflow | yes |
| Export any dataset | yes |
| Import to a reference dataset | yes, once unlocked |
| Import to a test dataset | yes |
| Import to a **reporter's** dataset | **no** |
| Import to the data collection | **no** |

A reporter's data can only be uploaded with that reporter's own key. There is no
unlock for it — it is a permission boundary, not a lock.
