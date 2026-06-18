# DataflowClient

A `DataflowClient` is scoped to a single dataflow and optionally a single
reporter. Obtain one via [`ReportnetClient.for_dataflow()`][reportnet.ReportnetClient.for_dataflow].

```python
df = client.for_dataflow(1619)          # dataflow scope only
ie = df.for_provider(42)               # further scoped to reporter 42
```

All methods automatically fill in `dataflow_id` (and `provider_id` when set).

::: reportnet.DataflowClient
