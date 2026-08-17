# DataflowClient

A `DataflowClient` is scoped to a single dataflow and optionally a single
reporter. Obtain one via [`ReportnetClient.for_dataflow()`][reportnet.ReportnetClient.for_dataflow].

```python
flow = client.for_dataflow(1619)          # dataflow scope only
ie = flow.for_provider(17)               # further scoped to reporter 17 (IE)
```

All methods automatically fill in `dataflow_id` (and `provider_id` when set).

::: reportnet.DataflowClient
