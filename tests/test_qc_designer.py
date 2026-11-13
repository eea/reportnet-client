"""QcDesigner (WP4): guards, whole-body updates and read-back.

A small in-memory fake of the rules service stands in for Reportnet, so each
write is visible to the next read and the read-back is real.
"""

import base64
import itertools
import json
import time

import httpx
import pytest

from reportnet import QcDesigner, ReportnetClient
from reportnet.exceptions import (
    DuplicateNameError,
    QcRuleNotEditableError,
    QcSqlError,
    SchemaDesignError,
    SchemaDesignNotPermittedError,
    SchemaReadbackError,
)

FLOW, DS, SCHEMA = 11468, 48100, "6af5cce0c6dc4400014d1f72"
TABLE_ID, RECORD_ID, FIELD_ID = "tbl-sites", "rec-sites", "fld-code"
SQL = 'SELECT * FROM dataset_48100."sites" WHERE sitecode IS NULL'


def _jwt() -> str:
    def enc(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{enc({'alg': 'none'})}.{enc({'exp': int(time.time()) + 3600})}.s"


class FakeRules:
    """Just enough of /rules (and the dataflow and schema reads) for read-back."""

    def __init__(self, router):
        self.ids = (f"rule{n:03d}" for n in itertools.count())
        self.rules: list[dict] = [
            {"ruleId": "auto1", "shortCode": "FT01", "ruleName": "auto", "type": "FIELD",
             "referenceId": FIELD_ID, "automatic": True, "enabled": True, "sqlSentence": None,
             "thenCondition": ["auto", "ERROR"], "description": ""},
            {"ruleId": "expr1", "shortCode": "EX01", "ruleName": "expression", "type": "FIELD",
             "referenceId": FIELD_ID, "automatic": False, "enabled": True, "sqlSentence": "",
             "expressionText": "( x MATCH ^a$ )", "thenCondition": ["e", "WARNING"],
             "description": ""},
        ]
        self.ignore_next_write = False   # simulate a write that did not land
        self.ignore_deletes = False
        r = router
        r.get(f"/dataflow/v1/{FLOW}").mock(return_value=httpx.Response(200, json={
            "id": FLOW, "name": "F", "bigData": True, "dataCollections": [],
            "designDatasets": [{"id": DS, "dataSetName": "Scratch", "datasetSchema": SCHEMA}]}))
        r.get(f"/dataschema/v1/datasetId/{DS}").mock(return_value=httpx.Response(200, json={
            "idDataSetSchema": SCHEMA, "nameDatasetSchema": "Scratch", "tableSchemas": [{
                "idTableSchema": TABLE_ID, "nameTableSchema": "Sites",
                "recordSchema": {"idRecordSchema": RECORD_ID, "fieldSchema": [
                    {"id": FIELD_ID, "name": "SiteCode", "type": "TEXT"}]}}]}))
        r.get(f"/rules/{SCHEMA}/dataflow/{FLOW}").mock(side_effect=lambda req: httpx.Response(
            200, json={"idDatasetSchema": SCHEMA, "rulesSchemaId": "rs",
                       "automaticQCsDefaultLevelError": "ERROR", "rules": self.rules}))
        self.create = r.put("/rules/createNewRule").mock(side_effect=self._create)
        self.update = r.put("/rules/updateRule").mock(side_effect=self._update)
        self.delete = r.delete("/rules/deleteRule").mock(side_effect=self._delete)
        self.run = r.post("/rules/runSqlRule").mock(return_value=httpx.Response(200, json=[]))
        self.validate = r.post("/rules/validateSqlRules").mock(return_value=httpx.Response(200))

    def _create(self, req):
        body = json.loads(req.content)
        if self.ignore_next_write:
            self.ignore_next_write = False
            body = {**body, "thenCondition": [body["thenCondition"][0], "INFO"]}
        self.rules.append({**body, "ruleId": next(self.ids), "verified": None})
        return httpx.Response(200)

    def _update(self, req):
        body = json.loads(req.content)
        if self.ignore_next_write:
            self.ignore_next_write = False
            return httpx.Response(200)
        self.rules = [dict(r, **body) if r["ruleId"] == body["ruleId"] else r
                      for r in self.rules]
        return httpx.Response(200)

    def _delete(self, req):
        if not self.ignore_deletes:
            rid = req.url.params["ruleId"]
            self.rules = [r for r in self.rules if r["ruleId"] != rid]
        return httpx.Response(200)


@pytest.fixture
def fake(mock_router):
    return FakeRules(mock_router)


@pytest.fixture
def qc(fake) -> QcDesigner:
    return ReportnetClient.from_tokens(_jwt(), "rt").for_dataflow(FLOW).qc(DS)


def add(qc, code="SQL01", **kw):
    args = {"name": "Site code", "sql": SQL, "on": "Sites", "message": "Missing code",
            "severity": "ERROR"}
    args.update(kw)
    return qc.add_sql_rule(code, **args)


# ── guards before any request ───────────────────────────────────────────────

def test_api_key_is_refused_before_any_request(mock_router, client):
    with pytest.raises(SchemaDesignNotPermittedError):
        client.for_dataflow(FLOW).qc(DS)
    assert not mock_router.calls


def test_only_design_datasets(fake):
    with pytest.raises(SchemaDesignError, match="not a design dataset"):
        ReportnetClient.from_tokens(_jwt(), "rt").for_dataflow(FLOW).qc(99999)


def test_sql_must_start_with_select_or_with(qc, fake):
    with pytest.raises(QcSqlError):
        add(qc, sql="DELETE FROM x")
    assert not fake.create.called
    add(qc, "SQL02", sql="  with t as (select 1) select * from t")


def test_unknown_severity_is_refused(qc, fake):
    with pytest.raises(SchemaDesignError, match="severity"):
        add(qc, severity="FATAL")
    assert not fake.create.called


def test_severity_is_case_insensitive(qc):
    assert add(qc, severity="warning").severity == "WARNING"


def test_duplicate_short_code_is_refused_case_insensitively(qc, fake):
    add(qc)
    with pytest.raises(DuplicateNameError):
        add(qc, "sql01")
    with pytest.raises(DuplicateNameError):
        add(qc, "ft01")  # also against automatic rules
    assert fake.create.call_count == 1


@pytest.mark.parametrize("call", [
    lambda qc: qc.update_rule("FT01", message="x"),
    lambda qc: qc.disable("FT01"),
    lambda qc: qc.enable("FT01"),
    lambda qc: qc.delete_rule("FT01"),
    lambda qc: qc.update_rule("EX01", message="x"),
    lambda qc: qc.delete_rule("EX01"),
])
def test_automatic_and_non_sql_rules_are_not_editable(qc, fake, call):
    with pytest.raises(QcRuleNotEditableError):
        call(qc)
    assert not fake.update.called and not fake.delete.called


def test_unknown_rule(qc):
    with pytest.raises(SchemaDesignError, match="No rule"):
        qc.disable("NOPE")


def test_unknown_table_or_field(qc, fake):
    with pytest.raises(SchemaDesignError, match="No table"):
        add(qc, on="Nowhere")
    with pytest.raises(SchemaDesignError, match="no field"):
        add(qc, on=("Sites", "Nope"))
    assert not fake.create.called


# ── targets and bodies ──────────────────────────────────────────────────────

def test_table_rule_body_matches_the_web_app(qc, fake):
    rule = add(qc)
    sent = json.loads(fake.create.calls.last.request.content)
    assert sent == {"automatic": False, "enabled": True, "type": "TABLE",
                    "referenceId": TABLE_ID, "ruleName": "Site code", "shortCode": "SQL01",
                    "description": "", "expressionText": None, "sqlSentence": SQL,
                    "thenCondition": ["Missing code", "ERROR"], "whenCondition": None,
                    "integrityVO": None}
    assert dict(fake.create.calls.last.request.url.params) == {"datasetId": str(DS)}
    assert (rule.type, rule.reference_id, rule.short_code) == ("TABLE", TABLE_ID, "SQL01")


def test_record_and_field_rules(qc, fake):
    assert add(qc, "R1", record=True).reference_id == RECORD_ID
    field_rule = add(qc, "F1", on=("sites", "sitecode"))
    assert (field_rule.type, field_rule.reference_id) == ("FIELD", FIELD_ID)
    assert "integrityVO" not in json.loads(fake.create.calls.last.request.content)


# ── updates and read-back ───────────────────────────────────────────────────

def test_update_sends_the_whole_rule_and_keeps_the_severity(qc, fake):
    add(qc, severity="WARNING")
    rule = qc.update_rule("sql01", message="Every site needs a code")
    sent = json.loads(fake.update.calls.last.request.content)
    assert sent["ruleId"] and sent["sqlSentence"] == SQL and sent["shortCode"] == "SQL01"
    assert sent["thenCondition"] == ["Every site needs a code", "WARNING"]
    assert (rule.message, rule.severity) == ("Every site needs a code", "WARNING")


def test_update_sql_is_checked(qc, fake):
    add(qc)
    with pytest.raises(QcSqlError):
        qc.update_rule("SQL01", sql="DROP TABLE sites")
    assert not fake.update.called


def test_disable_and_enable(qc, fake):
    add(qc)
    assert qc.disable("SQL01").enabled is False
    assert json.loads(fake.update.calls.last.request.content)["enabled"] is False
    assert qc.enable("SQL01").enabled is True


def test_rules_lists_sql_only(qc):
    add(qc)
    assert [r.short_code for r in qc.rules(sql_only=True)] == ["SQL01"]
    assert len(qc.rules()) == 3


def test_delete_checks_the_rule_is_gone(qc, fake):
    add(qc)
    qc.delete_rule("SQL01")
    assert dict(fake.delete.calls.last.request.url.params)["datasetId"] == str(DS)
    assert all(r["shortCode"] != "SQL01" for r in fake.rules)


def test_delete_that_did_not_land_is_reported(qc, fake):
    add(qc)
    fake.ignore_deletes = True
    with pytest.raises(SchemaReadbackError):
        qc.delete_rule("SQL01")


def test_create_that_read_back_differently_is_reported(qc, fake):
    fake.ignore_next_write = True   # the server stores severity INFO instead
    with pytest.raises(SchemaReadbackError) as info:
        add(qc, severity="ERROR")
    assert info.value.expected == {"severity": "ERROR"}
    assert info.value.actual == {"severity": "INFO"}


def test_update_that_did_not_land_is_reported(qc, fake):
    add(qc)
    fake.ignore_next_write = True
    with pytest.raises(SchemaReadbackError):
        qc.disable("SQL01")


# ── SQL helpers ─────────────────────────────────────────────────────────────

def test_test_sql_and_validate_all(qc, fake):
    assert qc.test_sql(SQL, provider_code="FR") == []
    assert dict(fake.run.calls.last.request.url.params)["runSQLAsProvider"] == "FR"
    with pytest.raises(QcSqlError):
        qc.test_sql("UPDATE x SET y = 1")
    qc.validate_all()
    assert dict(fake.validate.calls.last.request.url.params) == {
        "datasetId": str(DS), "datasetSchemaId": SCHEMA}


def test_schema_designer_offers_qc(fake):
    designer = ReportnetClient.from_tokens(_jwt(), "rt").for_dataflow(FLOW).design(DS)
    assert isinstance(designer.qc, QcDesigner) and designer.qc.schema_id == SCHEMA
