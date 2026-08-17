# Jobs

Imports, exports and validations are asynchronous: the API returns a job ID and
a polling URL, and the client polls until the job reaches a terminal status.
Every such call returns a `JobHandle`.

These live in `reportnet.jobs` — separately from [models](models.md), because a
`JobHandle` holds a live HTTP session and performs network I/O rather than
simply parsing a response.

```python
handle = flow.import_file(dataset_id=93953, file="data.csv")
handle.wait(poll_interval=5.0, timeout=300.0)

frames = flow.etl_export(dataset_id=93953).to_frames()
```

::: reportnet.JobHandle

::: reportnet.JobStatus
