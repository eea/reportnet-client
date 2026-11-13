# Spec: SQL QC rule editing in reportnet-client

Status: ready to implement. Written 2026-11-13 against `eea/reportnet-client` @ `18185dd`.

## 1. Goal

Add support to **list, create, update, enable/disable and delete SQL QC rules** on a
design dataset, plus the SQL helper calls (check, test-run, validate all).

In scope: rules whose logic is a `sqlSentence` (types `FIELD`, `RECORD`, `TABLE`).

Out of scope — do **not** implement:
- Expression-language rules (`( field MATCH ^regex$ )`, `whenCondition` trees).
- Relation / integrity rules (`integrityVO`).
- Automatic rules (`automatic: true`): no create, update, delete or enable.
- `updateAutomaticRule`, `updateAutomaticQCsDefaultLevelError`, QC import/export files.

## 2. Evidence and confidence

All endpoints come from the Reportnet 3 web app front end (`main.*.chunk.js`, sandbox,
2026-11-13), read on dataflow **11468**, design dataset **48099**,
schema id **`6af5c1cec6dc4400014d1f65`**.

| Item | Status |
|---|---|
| `GET /rules/{datasetSchemaId}/dataflow/{dataflowId}` | **Verified live** (200, login token). Already noted in `notes/api-notes.md`: API keys are refused. |
| All write and SQL-helper endpoints | **From front-end code only.** Not called yet. Phase 0 must verify. |
| Severity values `BLOCKER`, `ERROR`, `WARNING`, `INFO` | Confirmed by the public schema export (`public_schema.QcRule.severity`). |

Treat every "from code" item as a hypothesis until Phase 0 records the real request and
response in `notes/api-notes.md`.

## 3. IDs

| Name in this spec | What it is | Example (sandbox) |
|---|---|---|
| `dataflow_id` | Dataflow id | `11468` |
| `dataset_id` | **Design** dataset id (int) | `48099` |
| `schema_id` | Dataset schema id (Mongo hex string), `DesignDataset.schema_id` | `6af5c1cec6dc4400014d1f65` |
| `rule_id` | Rule id from the rules list | – |
| `reference_id` | Field schema id (`FIELD`), record schema id (`RECORD`, = `TableSchema.record_id`) or table schema id (`TABLE`) | – |

Get `schema_id` from `get_dataset_metabase` or the dataflow's `designDatasets`; get
`reference_id` from `get_schema(dataset_id=…)`.

## 4. Endpoints

Base URL: the client's normal API base (sandbox: `https://sandbox-api.reportnet.europa.eu`).
All need a **login token** (assume API keys get 403, as for `GET /rules/…`).

| Operation | Method | Path + query | Body | Client method |
|---|---|---|---|---|
| List rules | GET | `/rules/{schema_id}/dataflow/{dataflow_id}` | – | `get_rules` |
| Create rule | **PUT** | `/rules/createNewRule?datasetId={dataset_id}` | rule body (§5) | `create_rule` |
| Update rule (also enable/disable) | PUT | `/rules/updateRule?datasetId={dataset_id}` | rule body with `ruleId` | `update_rule` |
| Delete rule | DELETE | `/rules/deleteRule?datasetId={schema_id}&ruleId={rule_id}` | – | `delete_rule` |
| Check SQL (syntax / cost) | POST | `/rules/evaluateSqlRule?datasetId={dataset_id}` | `{"sqlRule": "<sql>"}` | `evaluate_sql_rule` |
| Test-run SQL | POST | `/rules/runSqlRule?datasetId={dataset_id}&showInternalFields={bool}` | `{"sqlRule": "<sql>"}` | `run_sql_rule` |
| Test-run SQL as provider | POST | as above + `&runSQLAsProvider={provider_code}` | `{"sqlRule": "<sql>"}` | `run_sql_rule(provider_code=…)` |
| Validate all SQL rules | POST | `/rules/validateSqlRules?datasetId={dataset_id}&datasetSchemaId={schema_id}` | – | `validate_sql_rules` |
| Rule history | GET | `/rules/historicInfo?datasetId={dataset_id}&ruleId={rule_id}` | – | `get_rule_history` |

Notes:
1. **Create is PUT**, not POST.
2. **Delete:** the query parameter is *named* `datasetId` but the front end puts the
   **schema id** in it. Verify in Phase 0. If the schema id fails, try the dataset id
   and record which one works.
3. **No enable endpoint.** Enable/disable = `updateRule` with the full rule and
   `enabled` changed.
4. The front end sends `sqlSentence` also as a query parameter on `runSqlRule`, but its
   URL template has no placeholder for it, so it is dropped. Send SQL in the body only.
5. The front end routes automatic rules to `PUT /rules/updateAutomaticRule/{datasetId}`.
   Out of scope; refuse automatic rules client-side.

## 5. Rule body (create / update)

Exactly what the front end sends for an SQL rule:

```json
{
  "ruleId": "<update only>",
  "automatic": false,
  "enabled": true,
  "type": "FIELD",
  "referenceId": "<field / record / table schema id>",
  "ruleName": "Site code exists in Sites",
  "shortCode": "SQL01",
  "description": "…",
  "expressionText": null,
  "sqlSentence": "SELECT … FROM dataset_48099.\"sites\" …",
  "thenCondition": ["Message shown to the reporter", "ERROR"],
  "whenCondition": null
}
```

- `thenCondition` = `[message, severity]`, in that order.
- For `TABLE` rules the front end also sends `"integrityVO": null`. Send it for `TABLE`.
- When `sqlSentence` is set, `whenCondition` is always `null`.
- Create response: unknown (record it in Phase 0). Do not depend on it; find the new
  rule by re-listing and matching `shortCode`.

## 6. List response

`GET /rules/{schema_id}/dataflow/{dataflow_id}` returns:

```text
{ idDatasetSchema, rulesSchemaId, automaticQCsDefaultLevelError, rules: [ … ] }
```

Each rule has: `ruleId`, `ruleName`, `shortCode`, `description`, `type`, `referenceId`,
`sqlSentence`, `sqlError`, `sqlCost`, `verified`, `enabled`, `automatic`,
`automaticType`, `expressionText`, `thenCondition`, `whenCondition`, `integrityVO`,
`activationGroup`.

An empty string `sqlSentence` means "no SQL" (front end maps `""` to `null`).

## 7. Implementation

Follow the existing schema-design pattern exactly (`client.py` low level,
`schema_design.py` safe high level, `api-notes.md` for quirks).

### 7.1 Model — `models.py`

New frozen dataclass `RuleDefinition` (do **not** reuse `public_schema.QcRule`; that one
is parsed from the public spreadsheet and has different fields).

```python
@dataclass(frozen=True)
class RuleDefinition:
    id: str                    # ruleId
    name: str                  # ruleName
    short_code: str            # shortCode
    description: str
    type: str                  # FIELD | RECORD | TABLE | DATASET
    reference_id: str          # referenceId
    sql: str | None            # sqlSentence ("" -> None)
    message: str               # thenCondition[0]
    severity: str              # thenCondition[1]
    enabled: bool
    automatic: bool
    verified: bool | None      # verified ("Valid" column)
    sql_error: str | None      # sqlError
    sql_cost: float | None     # sqlCost
    raw: Mapping[str, Any]     # the original dict, for full-body updates

    @property
    def is_sql(self) -> bool: ...
    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "RuleDefinition": ...
    def to_body(self) -> dict[str, Any]: ...   # §5 body, keeps unknown keys from raw
```

Also a `Severity` `StrEnum` (`BLOCKER`, `ERROR`, `WARNING`, `INFO`) and a small
`RuleSet` (`schema_id`, `rules_schema_id`, `rules: tuple[RuleDefinition, ...]`).
Export the new names from `__init__.py`.

### 7.2 Raw calls — `client.py`

New section "QC rules (custodian; login token only)" after schema design. One method per
row in §4. Rules:
- Writes go through `_schema_write` (login-token check, no retry, 5xx →
  `SchemaWriteUncertainError`). Reads use `self._http.get` but still call
  `_require_login_token`.
- Pass query values with `params=`, never string formatting.
- Keyword-only arguments, docstring line = `METHOD path — what it does`, as in the
  existing methods.

### 7.3 Safe helper — new `qc_design.py`

`QcDesigner`, created by `DataflowClient.qc(dataset_id)` and by
`SchemaDesigner.qc` (property). It holds no endpoint knowledge.

```python
designer = flow.qc(48099)
rule = designer.add_sql_rule(
    "SQL01", name="Site code exists",
    sql='SELECT … FROM dataset_48099."sites" …',
    on="Sites",              # table name / TableSchema -> TABLE rule
    # on=("Sites", "SiteCode") -> FIELD rule; record=True + table -> RECORD rule
    message="Unknown site code", severity="ERROR",
    enabled=True, check_sql=True,
)
designer.update_rule("SQL01", sql=..., message=..., severity=...)
designer.disable("SQL01"); designer.enable("SQL01")
designer.delete_rule("SQL01")
designer.rules(sql_only=True)            # -> list[RuleDefinition]
designer.test_sql(sql, provider_code=None)  # -> run_sql_rule result
designer.validate_all()
```

Guards (each one raises before any write):
- Login token only (reuse `SchemaDesignNotPermittedError`).
- Design dataset of this dataflow only (same check as `DataflowClient.design`).
- Rules are addressed by **short code** (case-insensitive) or `RuleDefinition`.
  Short code must be unique on create → `DuplicateNameError`.
- Refuse automatic rules and non-SQL rules on update/enable/disable/delete →
  new `QcRuleNotEditableError(SchemaDesignError)`.
- SQL must start with `SELECT` or `WITH` (reuse `public_schema._SQL_START`).
- `severity` must be a `Severity` value.
- `check_sql=True` (default) calls `evaluate_sql_rule` first and raises
  `QcSqlError` with the server message if the SQL is invalid. Record in Phase 0 what an
  invalid SQL response looks like.
- Updates send the **whole** body built from the current read-back rule plus the
  changes (same lesson as field updates).

Read-back after every write: re-list rules, find by short code, compare the changed
attributes, raise `SchemaReadbackError` on mismatch (delete: rule must be gone).
Return the read-back `RuleDefinition`.

### 7.4 Docs and notes

- `notes/api-notes.md`: add a "QC rules" section with the §4 table (column "Wrapped as")
  and every Phase 0 finding.
- `CHANGELOG.md`: new "Added" entry.
- `docs/`: one short reporter-facing page only if the maintainer asks; internals stay in
  `notes/`.

## 8. Work plan

**Phase 0 — live probe (do first, sandbox only).** Write `scripts/probe_qc_rules.py`
(parameters at the top: `DATAFLOW_ID = 11468`, `DATASET_ID = 48099`,
`SHORT_CODE = "RNCLIENT_PROBE"`). With a login token it must:
1. List rules; save the JSON.
2. `evaluateSqlRule` with a valid and an invalid SQL; save both responses.
3. Create one `TABLE` SQL rule (`SELECT * FROM dataset_48099."sites" WHERE 1=0`,
   severity `INFO`, short code `RNCLIENT_PROBE`); save the response; re-list.
4. Update its message; disable it; enable it; re-list after each.
5. `runSqlRule` with the rule SQL.
6. Delete it (schema id in `datasetId`; fall back to dataset id); re-list.
7. Try one write with an API key and record the status.

Log status code and body for each step to `notes/live-tests-qc-11468.json`. Never
touch rules the probe did not create. Always delete the probe rule in a `finally`.

**Phase 1** — models + raw client methods + respx unit tests for every method
(method, path, query, body).

**Phase 2** — `QcDesigner` + unit tests for every guard and the read-back.

**Phase 3** — integration test `tests/test_qc_design_integration.py`
(`@pytest.mark.integration`) that runs the full create → update → disable → enable →
delete cycle on dataset 48099 and cleans up.

## 9. Done when

- `uv run pytest`, `uv run ruff check src tests` and `uv run mypy src` pass.
- `uv run pytest --integration -m integration -k qc` passes on sandbox 11468.
- `notes/api-notes.md` lists every QC endpoint with "verified" or "not verified".
- No rule that the tests created is left on the sandbox dataset.
