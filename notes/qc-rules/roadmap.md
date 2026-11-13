# Roadmap: SQL QC rule editing

**For:** the owner, the PM and any agent resuming this work. **Status:**
2026-11-13. **Goal:** the success criteria in the [brief](brief.md#success-criteria-proposed-the-owner-approves-them-r-60).

Only the owner moves a work package to *ready*. The PM marks it *done* after
review and, if permitted, a commit.

## Work packages, in order

| WP | What | Acceptance check | Live? | State |
| --- | --- | --- | --- | --- |
| WP0 | Fix the misleading error: a failed token renewal must surface as `AuthError`, not `DiscoveryNotPermittedError` with a hint about reporter keys | a test that fails before the fix; Q1, Q2 | no | done: `LoginTokenError`; 3 of 4 new tests failed before the fix; 374 passed, 63 skipped; ruff and mypy 0 |
| WP1 | Phase 0 probe script `scripts/probe_qc_rules.py` (spec §8), written and dry-run checked offline | runs offline as far as the first request; logs no secrets (Q9) | no | done: dry run against an in-memory fake of the rules API, 4 of 4 cases pass (normal run; delete falls back to the dataset id; an echoed token blocks the record and exits 1; an existing probe rule stops the run before any write); ruff 0, mypy --strict 0 |
| WP2 | Owner runs the probe; PM records the findings in `notes/api-notes.md` | Q6, Q8, Q9 | **yes** | done 2026-11-13: completed; probe rule deleted; 0 token-like strings in the record; 7 endpoints verified, `runSqlRule` not conclusive, API-key write skipped |
| WP2b | Second probe: how an invalid rule looks after "validate all"; test-run SQL read-only on a dataset with data (Q-08) | Q6, Q8, Q9 | **yes** | done 2026-11-13: completed; both rules deleted; 0 token-like strings; only `runSqlRule` reached 33796. Invalid SQL is not detected by the API (D-06); `runSqlRule` is broken on 33796 by a Reportnet bug (D-07) |
| WP3 | Models and raw client methods (spec §7.1–7.2), shaped by the WP2 findings | Q1–Q4 | no | review: built and committed; 25 new tests; 399 passed, 63 skipped; ruff and mypy 0; src +213 lines, tests +135. `run_sql_rule`'s return value is not typed until WP2b shows its answer |
| WP4 | `QcDesigner` with guards and read-back (spec §7.3) | Q1, Q2, Q5 | no | review: built and committed. 26 tests against an in-memory fake; switching off read-back fails 2, switching off the editable guard fails 6. 425 passed, 63 skipped; ruff and mypy 0; src +271 lines, tests +207 |
| WP5 | Integration test, then the owner runs it | Q7, Q8, Q9 | **yes** | done 2026-11-13: passed live on 48100 in 3.7 s ([log](it-run.log)); other rules unchanged; 0 token-like strings |
| WP6 | `CHANGELOG.md` and notes | Q6 | no | done: changelog "Added" entry; "Wrapped as" column filled in `api-notes.md`; helpdesk draft [request_reportnet-helpdesk.md](request_reportnet-helpdesk.md) (Q-12, not sent) |

WP3 and WP4 can start from the front-end shapes in the spec while WP2 waits
for the owner (R-07), but they are not marked done until the WP2 findings
have been applied.

## Status against the success criteria (2026-11-13)

| # | Current value |
| --- | --- |
| Q1 | met: 425 passed, 64 skipped; the 370 earlier tests still pass; no existing test changed |
| Q2 | met: ruff 0, mypy (strict) 0 |
| Q3 | met: `Severity(str, Enum)`; no 3.11+ feature |
| Q4 | met: 25 tests in `tests/test_qc_rules.py`, one or more per endpoint |
| Q5 | met: 26 tests in `tests/test_qc_designer.py`. Switching off read-back fails 2; switching off the editable guard fails 6 |
| Q6 | met: `api-notes.md` "QC rules". 8 endpoints verified; `runSqlRule` and the API-key write are marked not verified |
| Q7 | met: `test_qc_rule_full_cycle` passed live |
| Q8 | met: both probes and the test deleted their rules; the test asserts that the other rules are unchanged |
| Q9 | met: 0 token-like strings in both probe records and the test log |

Size: `src` about 520 new lines (budget 700); tests about 495 (budget 700);
notes within budget. Passing these is not acceptance (R-64).

**After review (2026-11-13):** the probe records were redacted in the branch
history (server error ids, an internal host name and stack traces); the probe
script now redacts them itself. The custodian guide and API reference cover
QC rules. The live test now also changes a rule's SQL and adds a RECORD rule,
so Q7 had to be re-run. **Re-run 2026-11-13 by the owner: passed** on 48100
in 4.4 s ([log](it-run.log), local path removed); Q7 is met again. Open: the
owner's review, an independent reviewer, and permission to push and open a
pull request.

## Risks

- Every write and SQL-helper endpoint is known only from front-end code
  (spec §2).
- `deleteRule` may want the schema id or the dataset id (spec §4, note 2).
  The probe tries both, so one call may fail before the other works.
- If the probe stops part-way, the `finally` block must still delete
  `RNCLIENT_PROBE`. If the delete itself fails, the rule stays on the dataset
  until it is deleted in the web app.
- Login tokens go stale; see the token lesson in the [brief](brief.md#scope-and-authority).
