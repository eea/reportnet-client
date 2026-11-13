"""QC rule endpoints and models (WP3). Request shapes are the ones verified on
sandbox dataflow 11468, 2026-11-13 (notes/api-notes.md, "QC rules")."""

import base64
import json
import time

import httpx
import pytest

from reportnet import ReportnetClient, RuleDefinition, RuleSet, Severity
from reportnet.exceptions import SchemaDesignNotPermittedError, SchemaWriteUncertainError

DS = 48100
DF = 11468
SCHEMA_ID = "6af5cce0c6dc4400014d1f72"
RULE_ID = "6af70eaba7dcca00018c59f7"
TABLE_ID = "6af70eaac6dc4400014ec63e"

# One rule exactly as the sandbox listed it (keys and value types).
LISTED_RULE = {
    "ruleId": RULE_ID, "ruleName": "rnclient probe", "shortCode": "RNCLIENT_PROBE",
    "description": "Temporary rule", "type": "TABLE", "referenceId": TABLE_ID,
    "sqlSentence": 'SELECT * FROM dataset_48100."sites" WHERE 1=0', "sqlError": None,
    "sqlCost": 0.0, "verified": True, "enabled": True, "automatic": False,
    "automaticType": None, "expressionText": None,
    "thenCondition": ["rnclient probe message", "INFO"], "whenCondition": None,
    "integrityVO": None, "activationGroup": None, "hasHistoric": False,
    "referenceFieldSchemaPKId": None, "salience": None, "whenConditionMethod": None,
}
LISTING = {"idDatasetSchema": SCHEMA_ID, "rulesSchemaId": "6af5cce0c6dc4400014d1f73",
           "automaticQCsDefaultLevelError": "ERROR", "rules": [LISTED_RULE]}


def _jwt() -> str:
    def enc(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{enc({'alg': 'none'})}.{enc({'exp': int(time.time()) + 3600})}.s"


@pytest.fixture
def token_client():
    return ReportnetClient.from_tokens(_jwt(), "rt")


def body(route) -> dict:
    return json.loads(route.calls.last.request.content)


def params(route) -> dict:
    return dict(route.calls.last.request.url.params)


# ── models ───────────────────────────────────────────────────────────────────

def test_rule_set_parses_the_listing():
    rs = RuleSet.from_dict(LISTING)
    assert rs.schema_id == SCHEMA_ID and rs.default_automatic_severity == "ERROR"
    r = rs.rules[0]
    assert (r.id, r.short_code, r.type, r.reference_id) == (RULE_ID, "RNCLIENT_PROBE", "TABLE",
                                                            TABLE_ID)
    assert (r.message, r.severity, r.enabled, r.verified, r.sql_cost) == (
        "rnclient probe message", "INFO", True, True, 0.0)
    assert r.is_sql and not r.automatic
    assert rs.by_short_code("rnclient_probe") is r
    assert rs.by_short_code("nope") is None


def test_new_rule_fields_are_none_until_validated():
    r = RuleDefinition.from_dict({**LISTED_RULE, "verified": None, "sqlCost": None})
    assert r.verified is None and r.sql_cost is None


def test_empty_sql_sentence_means_no_sql():
    r = RuleDefinition.from_dict({**LISTED_RULE, "sqlSentence": ""})
    assert r.sql is None and not r.is_sql


def test_short_then_condition_does_not_crash():
    r = RuleDefinition.from_dict({**LISTED_RULE, "thenCondition": None})
    assert (r.message, r.severity) == ("", "")


def test_to_body_sends_the_web_app_keys_only():
    b = RuleDefinition.from_dict(LISTED_RULE).to_body(enabled=False)
    assert set(b) == {"ruleId", "automatic", "enabled", "type", "referenceId", "ruleName",
                      "shortCode", "description", "expressionText", "sqlSentence",
                      "thenCondition", "whenCondition", "integrityVO"}
    assert b["enabled"] is False and b["ruleId"] == RULE_ID and b["integrityVO"] is None
    assert "salience" not in b and "hasHistoric" not in b


def test_to_body_of_a_field_rule_has_no_integrity_vo():
    b = RuleDefinition.from_dict({**LISTED_RULE, "type": "FIELD"}).to_body()
    assert "integrityVO" not in b


def test_severity_values():
    assert [s.value for s in Severity] == ["BLOCKER", "ERROR", "WARNING", "INFO"]
    assert Severity("ERROR") == "ERROR"


# ── raw client methods ───────────────────────────────────────────────────────

def test_get_rules(mock_router, token_client):
    route = mock_router.get(f"/rules/{SCHEMA_ID}/dataflow/{DF}").mock(
        return_value=httpx.Response(200, json=LISTING))
    rs = token_client.get_rules(schema_id=SCHEMA_ID, dataflow_id=DF)
    assert route.called and rs.rules[0].id == RULE_ID


def test_create_rule_is_a_put_with_the_dataset_id(mock_router, token_client):
    route = mock_router.put("/rules/createNewRule").mock(return_value=httpx.Response(200))
    new = {"shortCode": "SQL01", "sqlSentence": "SELECT 1"}
    assert token_client.create_rule(dataset_id=DS, body=new) is None
    assert params(route) == {"datasetId": str(DS)} and body(route) == new


def test_update_rule(mock_router, token_client):
    route = mock_router.put("/rules/updateRule").mock(return_value=httpx.Response(200))
    b = RuleDefinition.from_dict(LISTED_RULE).to_body(enabled=False)
    token_client.update_rule(dataset_id=DS, body=b)
    assert params(route) == {"datasetId": str(DS)} and body(route) == b


def test_delete_rule_sends_the_numeric_dataset_id(mock_router, token_client):
    route = mock_router.delete("/rules/deleteRule").mock(return_value=httpx.Response(200))
    token_client.delete_rule(dataset_id=DS, rule_id=RULE_ID)
    assert params(route) == {"datasetId": str(DS), "ruleId": RULE_ID}


def test_evaluate_sql_rule_returns_the_cost(mock_router, token_client):
    route = mock_router.post("/rules/evaluateSqlRule").mock(
        return_value=httpx.Response(200, text="0.0"))
    assert token_client.evaluate_sql_rule(dataset_id=DS, sql="SELECT 1") == 0.0
    assert params(route) == {"datasetId": str(DS)} and body(route) == {"sqlRule": "SELECT 1"}


def test_run_sql_rule(mock_router, token_client):
    route = mock_router.post("/rules/runSqlRule").mock(
        return_value=httpx.Response(200, json={"rows": []}))
    assert token_client.run_sql_rule(dataset_id=DS, sql="SELECT 1") == {"rows": []}
    assert params(route) == {"datasetId": str(DS), "showInternalFields": "false"}
    assert body(route) == {"sqlRule": "SELECT 1"}


def test_run_sql_rule_as_provider(mock_router, token_client):
    route = mock_router.post("/rules/runSqlRule").mock(return_value=httpx.Response(200))
    assert token_client.run_sql_rule(dataset_id=DS, sql="SELECT 1", provider_code="FR",
                                     show_internal_fields=True) is None
    assert params(route) == {"datasetId": str(DS), "showInternalFields": "true",
                             "runSQLAsProvider": "FR"}


def test_validate_sql_rules(mock_router, token_client):
    route = mock_router.post("/rules/validateSqlRules").mock(return_value=httpx.Response(200))
    token_client.validate_sql_rules(dataset_id=DS, schema_id=SCHEMA_ID)
    assert params(route) == {"datasetId": str(DS), "datasetSchemaId": SCHEMA_ID}


def test_get_rule_history(mock_router, token_client):
    route = mock_router.get("/rules/historicInfo").mock(return_value=httpx.Response(200, json=[]))
    assert token_client.get_rule_history(dataset_id=DS, rule_id=RULE_ID) == []
    assert params(route) == {"datasetId": str(DS), "ruleId": RULE_ID}


def test_a_5xx_on_a_rule_write_is_uncertain(mock_router, token_client):
    mock_router.put("/rules/updateRule").mock(return_value=httpx.Response(503, text="x"))
    with pytest.raises(SchemaWriteUncertainError):
        token_client.update_rule(dataset_id=DS, body={"ruleId": RULE_ID})


@pytest.mark.parametrize("call", [
    lambda c: c.get_rules(schema_id=SCHEMA_ID, dataflow_id=DF),
    lambda c: c.create_rule(dataset_id=DS, body={}),
    lambda c: c.update_rule(dataset_id=DS, body={}),
    lambda c: c.delete_rule(dataset_id=DS, rule_id=RULE_ID),
    lambda c: c.evaluate_sql_rule(dataset_id=DS, sql="SELECT 1"),
    lambda c: c.run_sql_rule(dataset_id=DS, sql="SELECT 1"),
    lambda c: c.validate_sql_rules(dataset_id=DS, schema_id=SCHEMA_ID),
    lambda c: c.get_rule_history(dataset_id=DS, rule_id=RULE_ID),
])
def test_api_keys_are_refused_before_any_request(mock_router, client, call):
    with pytest.raises(SchemaDesignNotPermittedError):
        call(client)
    assert not mock_router.calls
