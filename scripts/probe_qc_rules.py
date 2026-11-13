"""Phase 0 probe: call each SQL QC rule endpoint once on the sandbox and record the answers.

Spec: notes/qc-rules/spec.md §8; decisions Q-02 and Q-04 in notes/qc-rules/decisions.md.

Needs a fresh login token pair (log out and in again in the web app first) in
RN3_SANDBOX_ACCESS_TOKEN and RN3_SANDBOX_REFRESH_TOKEN. Writes only one rule,
with short code RNCLIENT_PROBE, and always deletes it again. On the scratch
dataset it may also add a "Sites" table and run "validate all SQL rules".
Writes every request and answer to notes/live-tests-qc-11468.json, and refuses
to write the file if it would contain a token or key.

    uv run python scripts/probe_qc_rules.py
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

import reportnet

DATAFLOW_ID = 11468
DATASET_ID = 48100            # scratch dataset (Q-02); use 48099 only if the owner says so
SCRATCH_DATASETS = {48100}    # the only datasets where a table may be added or all rules validated
SHORT_CODE = "RNCLIENT_PROBE"
TABLE = "Sites"
OUTPUT = Path(__file__).resolve().parents[1] / "notes" / "live-tests-qc-11468.json"
BODY_LIMIT = 20_000
# The keys the web app sends for an SQL rule (spec §5).
RULE_KEYS = ("ruleId", "automatic", "enabled", "type", "referenceId", "ruleName", "shortCode",
             "description", "expressionText", "sqlSentence", "thenCondition", "whenCondition")


class Stop(Exception):
    """A stop condition: record it and end the run without working around it."""


class Probe:
    def __init__(self, http: httpx.Client) -> None:
        self.http = http
        self.steps: list[dict[str, Any]] = []
        self.outcome = "not finished"

    def call(self, step: str, method: str, path: str, *, params: dict[str, Any] | None = None,
             body: Any = None, http: httpx.Client | None = None) -> tuple[int | None, Any]:
        try:
            r = (http or self.http).request(method, path, params=params, json=body)
            status, text = r.status_code, r.text
        except httpx.HTTPError as exc:
            status, text = None, f"{type(exc).__name__}: {exc}"
        try:
            answer: Any = json.loads(text) if text else None
        except ValueError:
            answer = text[:BODY_LIMIT]
        self.steps.append({"step": step, "method": method, "path": path, "params": params,
                           "sent": body, "status": status, "answer": answer})
        print(f"  {step:34} {method:6} {path} -> {status}")
        return status, answer


def probe_rules(probe: Probe, rules_path: str) -> list[dict[str, Any]]:
    status, listing = probe.call("list rules", "GET", rules_path)
    if status != 200 or not isinstance(listing, dict):
        raise Stop(f"listing the rules answered {status}")
    return list(listing.get("rules") or [])


def mine(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rules if str(r.get("shortCode", "")).casefold() == SHORT_CODE.casefold()]


def rule_body(rule: dict[str, Any], **changes: Any) -> dict[str, Any]:
    body = {k: rule.get(k) for k in RULE_KEYS}
    if rule.get("type") == "TABLE":
        body["integrityVO"] = None
    body.update(changes)
    return body


def run(client: reportnet.ReportnetClient, probe: Probe, api_key_http: httpx.Client | None) -> None:
    flow = client.for_dataflow(DATAFLOW_ID)
    ds = next((d for d in flow.get_design_datasets() if d.id == DATASET_ID), None)
    if ds is None:
        raise Stop(f"{DATASET_ID} is not a design dataset of dataflow {DATAFLOW_ID}")
    designer = flow.design(DATASET_ID)
    tables = designer.schema().tables
    table = next((t for t in tables if t.name.casefold() == TABLE.casefold()), None)
    if table is None:
        if DATASET_ID not in SCRATCH_DATASETS:
            raise Stop(f"dataset {DATASET_ID} has no table {TABLE!r} and is not a scratch dataset")
        table = designer.add_table(TABLE)
        designer.add_field(table, "SiteCode", "TEXT", pk=True, required=True)
        print(f"  added table {TABLE!r} to scratch dataset {DATASET_ID}")

    rules_path = f"/rules/{ds.schema_id}/dataflow/{DATAFLOW_ID}"
    if mine(probe_rules(probe, rules_path)):
        raise Stop(f"a rule {SHORT_CODE} already exists; delete it in the web app first")

    sql = f'SELECT * FROM dataset_{DATASET_ID}."{TABLE.lower()}" WHERE 1=0'
    evaluate = "/rules/evaluateSqlRule"
    probe.call("evaluate valid SQL", "POST", evaluate, params={"datasetId": DATASET_ID},
               body={"sqlRule": sql})
    probe.call("evaluate valid SQL, table as named", "POST", evaluate,
               params={"datasetId": DATASET_ID},
               body={"sqlRule": f'SELECT * FROM dataset_{DATASET_ID}."{TABLE}" WHERE 1=0'})
    probe.call("evaluate invalid SQL", "POST", evaluate, params={"datasetId": DATASET_ID},
               body={"sqlRule": "SELECT FROM nowhere WHERE"})

    try:
        new = {"automatic": False, "enabled": True, "type": "TABLE", "referenceId": table.id,
               "ruleName": "rnclient probe", "shortCode": SHORT_CODE,
               "description": "Temporary rule from scripts/probe_qc_rules.py",
               "expressionText": None, "sqlSentence": sql,
               "thenCondition": ["rnclient probe message", "INFO"], "whenCondition": None,
               "integrityVO": None}
        probe.call("create rule", "PUT", "/rules/createNewRule", params={"datasetId": DATASET_ID},
                   body=new)
        found = mine(probe_rules(probe, rules_path))
        if not found:
            raise Stop("the created rule was not found by its short code")
        rule = found[0]

        for step, changes in (
            ("update message", {"thenCondition": ["rnclient probe message, updated", "INFO"]}),
            ("disable", {"enabled": False}),
            ("enable", {"enabled": True}),
        ):
            probe.call(step, "PUT", "/rules/updateRule", params={"datasetId": DATASET_ID},
                       body=rule_body(rule, **changes))
            rule = (mine(probe_rules(probe, rules_path)) or [rule])[0]

        probe.call("run SQL", "POST", "/rules/runSqlRule",
                   params={"datasetId": DATASET_ID, "showInternalFields": "false"},
                   body={"sqlRule": sql})
        probe.call("rule history", "GET", "/rules/historicInfo",
                   params={"datasetId": DATASET_ID, "ruleId": rule.get("ruleId")})
        if DATASET_ID in SCRATCH_DATASETS:
            probe.call("validate all SQL rules", "POST", "/rules/validateSqlRules",
                       params={"datasetId": DATASET_ID, "datasetSchemaId": ds.schema_id})

        if api_key_http is not None:
            probe.call("create rule with an API key", "PUT", "/rules/createNewRule",
                       params={"datasetId": DATASET_ID}, body=new, http=api_key_http)
    finally:
        cleanup(probe, rules_path, ds.schema_id)


def cleanup(probe: Probe, rules_path: str, schema_id: str) -> None:
    """Delete every RNCLIENT_PROBE rule; none existed when the run started."""
    for rule in mine(probe_rules(probe, rules_path)):
        rid = rule.get("ruleId")
        status, _ = probe.call("delete rule (schema id)", "DELETE", "/rules/deleteRule",
                               params={"datasetId": schema_id, "ruleId": rid})
        if status is None or status >= 300:
            probe.call("delete rule (dataset id)", "DELETE", "/rules/deleteRule",
                       params={"datasetId": DATASET_ID, "ruleId": rid})
    left = mine(probe_rules(probe, rules_path))
    if left:
        raise Stop(f"{len(left)} {SHORT_CODE} rule(s) could not be deleted; delete in the web app")


def write(probe: Probe, secrets: list[str]) -> bool:
    record = {"run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "dataflow_id": DATAFLOW_ID, "dataset_id": DATASET_ID, "short_code": SHORT_CODE,
              "outcome": probe.outcome, "steps": probe.steps}
    text = json.dumps(record, indent=2, ensure_ascii=False)
    if any(s and s in text for s in secrets):
        print("STOP: a token or key appears in the record; nothing was written. "
              "Log out of the web app to end the session.")
        return False
    OUTPUT.write_text(text + "\n", encoding="utf-8")
    print(f"record: {OUTPUT}")
    return True


def main() -> int:
    access = os.environ.get("RN3_SANDBOX_ACCESS_TOKEN", "").strip()
    refresh = os.environ.get("RN3_SANDBOX_REFRESH_TOKEN", "").strip()
    if not access or not refresh:
        print("Set RN3_SANDBOX_ACCESS_TOKEN and RN3_SANDBOX_REFRESH_TOKEN first.")
        return 2
    client = reportnet.ReportnetClient.from_tokens(access, refresh, sandbox=True)
    api_key = ""
    try:
        api_key = reportnet.get_key(DATAFLOW_ID, sandbox=True)
    except Exception:
        print("  step 7 skipped: no sandbox API key in the keyring (Q-04)")
    api_key_http = (reportnet.ReportnetClient(api_key, base_url=reportnet.SANDBOX_URL)._http._client
                    if api_key else None)
    probe = Probe(client._http._client)  # raw httpx client: records every answer without raising
    try:
        run(client, probe, api_key_http)
        probe.outcome = "completed"
    except Stop as exc:
        probe.outcome = f"stopped: {exc}"
    except reportnet.ReportnetError as exc:
        probe.outcome = f"stopped: {type(exc).__name__}: {exc}"
    finally:
        secrets = [access, refresh, api_key]
        if client.tokens is not None:
            secrets += [client.tokens.access_token, client.tokens.refresh_token]
        if not write(probe, secrets):
            probe.outcome = "stopped: a secret appeared in an answer; record not written"
    print(f"OUTCOME: {probe.outcome}")
    return 0 if probe.outcome == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
