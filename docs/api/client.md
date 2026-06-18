# ReportnetClient

The top-level client. One instance per API key. Obtain a
[`DataflowClient`](dataflow-client.md) via [`for_dataflow()`][reportnet.ReportnetClient.for_dataflow]
to avoid repeating `dataflow_id` on every call.

::: reportnet.ReportnetClient
