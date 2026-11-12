# Roadmap: schema design for custodians

**For:** the owner, the PM and any agent resuming this work. **Status:**
2026-11-12. **Goal:** the success criteria in the [brief](brief.md#success-criteria).

Work packages follow the order of the technical brief (§12). Each one ends
with the full unit test suite, `ruff` and `mypy` green. Nothing is committed
until the owner authorises it ([brief](brief.md#roles-and-permissions)).

## Work packages, in order

| WP | What | Acceptance check | State |
| --- | --- | --- | --- |
| WP1 | Fix `SANDBOX_URL`; parse `fieldSchema: null` | S1, S2, S3 | review — built and checked 2026-11-12; not committed |
| WP2 | `TokenAuth`, `from_tokens()`, `from_credentials()` (experimental), `refresh_tokens()`, log redaction | S1, S4 | review — as above |
| WP3 | 16 schema-design methods on `ReportnetClient` | S1, S5 | review — as above |
| WP4 | Model fields and `FieldSchema.to_update_payload()` | S1, S3 | review — as above |
| WP5 | `SchemaDesigner`; `create_design_dataset()`, `design()` | S1, S6 | review — as above |
| WP6 | Integration tests on sandbox 11468 | S8 | review — written; skip cleanly without tokens; **not run live** |
| WP8 | Live test on the CWS, new session | S8 | ready — [instructions](cws-test-instructions.md) |
| WP7 | Docs, notes, changelog, mkdocs nav | S9 | review — `mkdocs build --strict` passes |

Packages stay in *review* until the owner authorises commits (R-02); the PM
marks them *done* after committing.

## Status against the success criteria (2026-11-12)

| # | Current value |
| --- | --- |
| S1 | 300 of 300 earlier tests pass; one line changed in one existing test (D-04). Suite: 370 passed, 63 skipped |
| S2 | met; `test_sandbox_url_is_the_api_host_not_the_web_app` |
| S3 | met; two tests in `tests/test_schema.py` |
| S4 | met; 17 tests in `tests/test_token_auth.py`. The log test was shown to fail with redaction switched off |
| S5 | met; 25 tests in `tests/test_schema_design.py` |
| S6 | met; 20 tests in `tests/test_schema_designer.py` against an in-memory fake. Switching off the data guard fails 3 tests; switching off read-back fails 1 |
| S7 | met; ruff 0, mypy (strict) 0 |
| S8 | **blocked**: written, not run. This machine cannot reach the sandbox: on 2026-11-12 neither `sandbox-api.reportnet.europa.eu` nor `sandbox.reportnet.europa.eu` resolved in DNS (curl exit 6), while `api.reportnet.europa.eu` answered 401. The sandbox is VPN-only; the test runs on the common workspace from [cws-test-instructions.md](cws-test-instructions.md) (D-11) |
| S9 | met, pending the owner's reading |

## Size

Over the budget in the brief: new source ≈ 1,360 lines (budget 900; about half
is docstrings with examples, as in the rest of `client.py`), tests ≈ 1,035
(budget 700; most of the excess is the in-memory fake), docs and notes ≈ 220
(budget 300). The owner decides whether to accept this or ask for a cut.

## Known risks (facts not yet verified live)

- Updating a LINK field sends back `referencedField` as read, including the
  extra keys GET adds (`labelId`, `tableSchemaName`, …). Whether PUT accepts
  them is not known; the web app's body for this case was not captured.
- On Citus (non-BigData) dataflows the data check uses import statistics,
  which miss manual edits; the designer warns when it does this.
- `from_credentials()` and token-refresh timing are unit-tested only.

## What the owner is asked for

See the [quick answers](decisions.md#quick-answers).
