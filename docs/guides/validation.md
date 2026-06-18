# Validate a dataset

## Trigger validation

```python
ie = client.for_dataflow(1619).for_provider(42)

handle = ie.add_validation_job(dataset_id=93953)
handle.wait(poll_interval=10.0, timeout=600.0)
```

If another job is already running on the dataset the API returns HTTP 423,
which raises [`DatasetLockedError`][reportnet.DatasetLockedError]. Either
wait and retry, or catch it explicitly:

```python
from reportnet import DatasetLockedError

try:
    handle = ie.add_validation_job(dataset_id=93953)
except DatasetLockedError:
    print("Dataset busy — try again shortly")
```

## Read validation results

### BigData datasets

```python
results = ie.list_group_validations_dl(dataset_id=93953)
# {"validations": [...], "totalRecords": 12, ...}
```

### Citus datasets

```python
results = ie.list_group_validations(dataset_id=93953)
```

## Download a release snapshot

After data has been officially released/submitted, you can download the
validation results for that snapshot as CSV bytes:

```python
csv_bytes = ie.download_validation_snapshot(
    snapshot_id=7,
    dataset_id=93953,
)
with open("validation_snapshot.csv", "wb") as f:
    f.write(csv_bytes)
```

## Release history

```python
releases = ie.list_historic_releases(dataset_id=93953)
for r in releases:
    print(r.get("releaseDate"), r.get("status"))
```
