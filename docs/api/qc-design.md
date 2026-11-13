# QC rules

For custodians writing SQL quality rules on a design dataset. Needs a login
token, not an API key: create the client with
[`ReportnetClient.from_tokens()`][reportnet.ReportnetClient.from_tokens].
See [Writing SQL QC rules](../guides/custodians.md#writing-sql-qc-rules) for a
walk-through, including what Reportnet does **not** check.

```python
qc = client.for_dataflow(11468).qc(48100)
qc.add_sql_rule("SITE01", name="Site code present", on="Sites",
                sql='SELECT * FROM dataset_48100."sites" WHERE sitecode IS NULL',
                message="Every site needs a code", severity="ERROR")
```

::: reportnet.QcDesigner

::: reportnet.RuleDefinition

::: reportnet.RuleSet

::: reportnet.Severity

## Raw client methods

One [`ReportnetClient`][reportnet.ReportnetClient] method per endpoint, without
the designer's guards or read-back.

::: reportnet.ReportnetClient.get_rules

::: reportnet.ReportnetClient.create_rule

::: reportnet.ReportnetClient.update_rule

::: reportnet.ReportnetClient.delete_rule

::: reportnet.ReportnetClient.evaluate_sql_rule

::: reportnet.ReportnetClient.run_sql_rule

::: reportnet.ReportnetClient.validate_sql_rules

::: reportnet.ReportnetClient.get_rule_history
