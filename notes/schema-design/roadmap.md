# Roadmap: schema design for custodians

**For:** the owner, the PM and any agent resuming this work. **Status:**
2026-11-12. **Goal:** the success criteria in the [brief](brief.md#success-criteria).

Work packages follow the order of the technical brief (§12). Each one ends
with the full unit test suite, `ruff` and `mypy` green. Nothing is committed
until the owner authorises it ([brief](brief.md#roles-and-permissions)).

## Work packages, in order

| WP | What | Acceptance check | State |
| --- | --- | --- | --- |
| WP1 | Fix `SANDBOX_URL`; parse `fieldSchema: null` | S1, S2, S3 | done — `99f6e85`, pushed |
| WP2 | `TokenAuth`, `from_tokens()`, `from_credentials()` (experimental), `refresh_tokens()`, log redaction | S1, S4 | done — `310bc29`, pushed |
| WP4 | Model fields and `FieldSchema.to_update_payload()` | S1, S3 | done — `f41c06b`, pushed |
| WP3 | 16 schema-design methods on `ReportnetClient` | S1, S5 | done — `7908ff9`, pushed |
| WP5 | `SchemaDesigner`; `create_design_dataset()`, `design()` | S1, S6 | done — `e54c2d5`, pushed |
| WP6 | Integration tests on sandbox 11468 | S8 | done — `09c812b`, pushed; skip cleanly without tokens; **not run live** (that is WP8) |
| WP7 | Docs, notes, changelog, mkdocs nav | S9 | done — `3eb4543`, `7726eeb`, pushed; waiting for the owner's reading |
| WP8 | Live test on the sandbox | S8 | review: passed on 2026-11-12 on the laptop over the VPN, not the CWS ([report](cws-test-report-2026-11-12.md)); not committed |

Committed and pushed on 2026-11-12 under D-10. "Done" means reviewed by the PM
and committed. It is not acceptance (R-64).

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
| S8 | **met on 2026-11-12**: `test_schema_design_full_cycle` passed against sandbox 11468 (scratch dataset 48100); see the [report](cws-test-report-2026-11-12.md). Token renewal against the real server is still untested. Earlier status: blocked: written, not run. This machine cannot reach the sandbox: on 2026-11-12 neither `sandbox-api.reportnet.europa.eu` nor `sandbox.reportnet.europa.eu` resolved in DNS (curl exit 6), while `api.reportnet.europa.eu` answered 401. The sandbox is VPN-only; the test runs on the common workspace from [cws-test-instructions.md](cws-test-instructions.md) (D-11) |
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
- **Seen live, 2026-11-12 15:44** (Agglomeration build, tokens copied from a
  web-app tab that had been idle for about 20 min): the first request got 401,
  and the refresh got **HTTP 500** from `POST /user/refreshToken`. Not yet known
  whether the cause was an expired refresh token or the request shape. Nothing
  was created. Two more runs failed the same way: one copied after a page reload,
  one with the tab closed after copying. Checked at 15:55: the sandbox is up,
  and `POST /user/refreshToken` answers **500 to a made-up token**, so a 500
  there means "token not valid", not a wrong request. The login tokens are
  opaque (45–46 characters, not JWTs), so the client cannot know when they
  expire. A fourth run with the tab left open (the pattern that worked at
  15:24) also failed, which rules out "reload or close invalidates the pair".
  Current hypothesis (not checked): after 15:27 the pair in the browser's
  session storage was already dead. Either a renewal during the live test
  rotated it, or the web app's own renewal failed, while the UI still showed
  the user as logged in. Test: log out, log in again, copy, run.
  **Result, 15:57:** after a fresh login the same build worked first time. That
  supports the hypothesis without proving it. Practical rule until it is
  checked: log out and log in before copying tokens.
- **`POINT` fields can be created through the API** (first time, 2026-11-12):
  design dataset 48105 `SpatialPoints`, table `Agglomeration`, 18 fields,
  read back as specified. See [D-13](decisions.md).
- **Bug:** `DataflowClient.get_dataflow_contents` wraps that `AuthError` in
  `DiscoveryNotPermittedError`, whose message about reporter keys is wrong for
  a failed renewal of a login token. Fix in its own work package, with a test
  that fails before the fix.

## What the owner is asked for

See the [quick answers](decisions.md#quick-answers).
