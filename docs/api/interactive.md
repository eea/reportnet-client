# Interactive & visualisation

Helpers for notebooks and UIs. Kept out of the client layers deliberately —
presentation concerns don't belong in the transport code — but re-exported at
the top level, so `reportnet.connect_interactive` works as before.

## connect_interactive

A one-call, non-raising connect helper for interactive tools (used by the
[example notebooks](../notebooks.md)) — returns `(flow, error_message)`
instead of raising, so callers can render the error directly in a UI.

::: reportnet.connect_interactive

## dataflow_to_mermaid

The renderer behind [`DataflowClient.to_mermaid()`][reportnet.DataflowClient.to_mermaid].
It is a pure function over already-fetched models, so you can call it with your
own data — or test it — without an API key.

```python
contents = flow.get_dataflow_contents()          # one request
diagram = reportnet.dataflow_to_mermaid(
    contents.info,
    reporting_datasets=contents.reporting_datasets,
    reference_datasets=contents.reference_datasets,
)
```

::: reportnet.dataflow_to_mermaid
