"""Live SQL QC rule cycle on the Reportnet 3 **sandbox**, dataflow 11468.

Run with a fresh login token pair (log out and in again in the web app first):
    RN3_SANDBOX_ACCESS_TOKEN=... RN3_SANDBOX_REFRESH_TOKEN=... \\
        uv run pytest --integration -m integration -k qc -v -s

Skipped if the tokens are missing.

**This writes to a shared sandbox**, but only in scratch design dataset 48100,
and only rules whose short code starts with ``RNCLIENT_IT_``. They are deleted
again even if the test fails. The test checks that every other rule of the
dataset is unchanged afterwards.
"""

import os
import time

import pytest

import reportnet
from reportnet.exceptions import DuplicateNameError, QcRuleNotEditableError

DATAFLOW_ID = 11468
DATASET_ID = 48100            # scratch (decision Q-02); it has table Sites with SiteCode
PREFIX = "RNCLIENT_IT_"


@pytest.fixture(scope="module")
def qc():
    access = os.environ.get("RN3_SANDBOX_ACCESS_TOKEN")
    refresh = os.environ.get("RN3_SANDBOX_REFRESH_TOKEN")
    if not (access and refresh):
        pytest.skip("RN3_SANDBOX_ACCESS_TOKEN / RN3_SANDBOX_REFRESH_TOKEN not set")
    client = reportnet.ReportnetClient.from_tokens(access, refresh, sandbox=True)
    return client.for_dataflow(DATAFLOW_ID).qc(DATASET_ID)


def _others(qc):
    """Every rule the test did not create, as comparable tuples."""
    return sorted((r.id, r.short_code, r.enabled, r.message, r.severity, r.sql)
                  for r in qc.rules() if not r.short_code.upper().startswith(PREFIX))


def _cleanup(qc):
    left = [r for r in qc.rules() if r.short_code.upper().startswith(PREFIX)]
    for rule in left:
        qc._client.delete_rule(dataset_id=DATASET_ID, rule_id=rule.id)
    return len(left)


@pytest.mark.integration
def test_qc_rule_full_cycle(qc):
    assert not [r for r in qc.rules() if r.short_code.upper().startswith(PREFIX)], (
        "RNCLIENT_IT_ rules are left from an earlier run; delete them in the web app")
    before = _others(qc)
    stamp = time.strftime("%H%M%S")
    table_code, field_code, record_code = (f"{PREFIX}T{stamp}", f"{PREFIX}F{stamp}",
                                           f"{PREFIX}R{stamp}")
    sql = f'SELECT * FROM dataset_{DATASET_ID}."sites" WHERE 1=0'
    try:
        rule = qc.add_sql_rule(table_code, name="rnclient it table", sql=sql, on="Sites",
                               message="rnclient it", severity="INFO")
        assert (rule.type, rule.enabled, rule.severity) == ("TABLE", True, "INFO")
        print(f"\n  created {table_code} ({rule.id})")

        with pytest.raises(DuplicateNameError):
            qc.add_sql_rule(table_code.lower(), name="dup", sql=sql, on="Sites",
                            message="dup", severity="INFO")

        rule = qc.update_rule(table_code, message="rnclient it, updated", severity="WARNING")
        assert (rule.message, rule.severity, rule.sql) == ("rnclient it, updated", "WARNING", sql)

        new_sql = f'SELECT * FROM dataset_{DATASET_ID}."sites" WHERE sitecode IS NULL'
        rule = qc.update_rule(table_code, sql=new_sql)
        assert (rule.sql, rule.message, rule.severity) == (new_sql, "rnclient it, updated",
                                                           "WARNING")
        assert qc.disable(table_code).enabled is False
        assert qc.enable(table_code).enabled is True

        field = qc.add_sql_rule(field_code, name="rnclient it field", sql=sql,
                                on=("Sites", "SiteCode"), message="field", severity="INFO")
        assert field.type == "FIELD"

        record = qc.add_sql_rule(record_code, name="rnclient it record", sql=sql, on="Sites",
                                 record=True, message="record", severity="INFO")
        assert record.type == "RECORD"

        automatic = [r for r in qc.rules() if r.automatic]
        if automatic:
            with pytest.raises(QcRuleNotEditableError):
                qc.disable(automatic[0])

        qc.delete_rule(record_code)
        qc.delete_rule(field_code)
        qc.delete_rule(table_code)
    finally:
        leftover = _cleanup(qc)
    assert leftover == 0, f"{leftover} rule(s) were left and removed by the clean-up"
    assert _others(qc) == before, "a rule the test did not create has changed"
