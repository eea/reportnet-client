# ReportnetClient

The top-level client. One instance per API key. Obtain a
[`DataflowClient`](dataflow-client.md) via [`for_dataflow()`][reportnet.ReportnetClient.for_dataflow]
to avoid repeating `dataflow_id` on every call.

::: reportnet.ReportnetClient

## connect_interactive

A one-call, non-raising connect helper for interactive tools (used by the
[example notebooks](../notebooks.md)) — returns `(flow, error_message)`
instead of raising, so callers can render the error directly in a UI.

::: reportnet.connect_interactive
