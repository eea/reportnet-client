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
| WP2b | Second probe: how an invalid rule looks after "validate all"; test-run SQL read-only on a dataset with data (Q-08) | Q6, Q8, Q9 | **yes** | ready (owner, 2026-11-13) |
| WP3 | Models and raw client methods (spec §7.1–7.2), shaped by the WP2 findings | Q1–Q4 | no | proposed |
| WP4 | `QcDesigner` with guards and read-back (spec §7.3) | Q1, Q2, Q5 | no | proposed |
| WP5 | Integration test, then the owner runs it | Q7, Q8, Q9 | **yes** | proposed |
| WP6 | `CHANGELOG.md` and notes | Q6 | no | proposed |

WP3 and WP4 can start from the front-end shapes in the spec while WP2 waits
for the owner (R-07), but they are not marked done until the WP2 findings
have been applied.

## Risks

- Every write and SQL-helper endpoint is known only from front-end code
  (spec §2).
- `deleteRule` may want the schema id or the dataset id (spec §4, note 2).
  The probe tries both, so one call may fail before the other works.
- If the probe stops part-way, the `finally` block must still delete
  `RNCLIENT_PROBE`. If the delete itself fails, the rule stays on the dataset
  until it is deleted in the web app.
- Login tokens go stale; see the token lesson in the [brief](brief.md#scope-and-authority).
