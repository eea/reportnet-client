# Schema design

For custodians designing a dataflow. Needs a login token, not an API key:
create the client with
[`ReportnetClient.from_tokens()`][reportnet.ReportnetClient.from_tokens].
See [Designing schemas](../guides/custodians.md#designing-schemas) for a walk-through.

```python
designer = client.for_dataflow(11468).design(48097)
sites = designer.add_table("Sites", mandatory=True)
```

::: reportnet.SchemaDesigner

::: reportnet.TokenPair

::: reportnet.TokenAuth
