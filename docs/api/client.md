# ReportnetClient

The top-level client. One instance per API key. Obtain a
[`DataflowClient`](dataflow-client.md) via [`for_dataflow()`][reportnet.ReportnetClient.for_dataflow]
to avoid repeating `dataflow_id` on every call.

`ReportnetClient` owns every quirk that belongs to an *endpoint* — URL shape,
parameter names, response oddities and API version selection — so calling any
method here directly is always correct. `DataflowClient` adds only *scoping*:
which IDs get filled in when you omit them.

!!! tip "Avoid repeated round-trips"
    `get_dataflow`, `get_reporting_datasets`, `get_reference_datasets` and
    `get_test_datasets` all read the same `/dataflow/v1/{id}` endpoint. Use
    [`get_dataflow_contents()`][reportnet.ReportnetClient.get_dataflow_contents]
    when you need more than one of them.

::: reportnet.ReportnetClient

`connect_interactive()` used to be documented here; it now lives on the
[Interactive & visualisation](interactive.md) page.
