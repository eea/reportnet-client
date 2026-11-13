# Project brief: SQL QC rule editing

**For:** the owner, the PM and any agent resuming this work. **Status:**
2026-11-13. The success criteria were approved by the owner on 2026-11-13 (Q-01).
**Follows:** `eea/ai-reporting-workflows` at commit `aec66fe` (no release tag
yet). **Source:** [spec.md](spec.md), a copy of the owner's spec, written
2026-11-13 against `main` @ `18185dd`. Cited below as "spec §n".

## Objective

Let a custodian list, create, update, enable, disable and delete **SQL** QC
rules on a design dataset from Python. Also wrap the SQL helper calls: check
SQL, test-run SQL and validate all rules. Expression rules, relation rules
and automatic rules are out of scope (spec §1).

Completion means code, unit tests, one integration test and notes on branch
`feat/qc-rules`, reviewed and ready for the owner to open a pull request.

## Workflow

None of the library's four workflows fits a code library. As with the
[schema-design project](../schema-design/brief.md), this project follows the
library's general rules and this repository's `CONTRIBUTING.md`.

## Success criteria

| # | Criterion | Target | Evidence | Who checks |
| --- | --- | --- | --- | --- |
| Q1 | Existing behaviour kept | the 370 unit tests that pass on `18185dd` still pass, none changed | `uv run pytest` | PM |
| Q2 | Static checks | `ruff check src tests` and `mypy src` (strict): 0 errors | command output | PM |
| Q3 | Python 3.10 still supported | no `StrEnum` or other 3.11+ feature; `Severity` follows the `FieldType(str, Enum)` pattern | code review | PM |
| Q4 | Every endpoint in spec §4 has its client method | one unit test per method checks the method, path, query and body | `tests/test_qc_rules.py` | PM |
| Q5 | Every guard in spec §7.3 is enforced | one unit test per guard; read-back is tested against an in-memory fake | `tests/test_qc_designer.py` | PM |
| Q6 | Facts recorded from the live API | `notes/api-notes.md` marks every QC endpoint "verified" or "not verified", with the Phase 0 findings | file | PM, owner |
| Q7 | Live cycle | `pytest --integration -m integration -k qc` passes on sandbox 11468 | test output | owner runs it, PM checks the log |
| Q8 | Clean sandbox | no rule created by the probe or the tests is left behind; no other rule is touched | rule list before and after | PM |
| Q9 | No secrets | no token in any file, log or message, including the Phase 0 JSON | token-pattern scan | PM |

Passing these is not acceptance (R-64).

## Size budget

`src` ≤ 700 new lines, tests ≤ 700, notes ≤ 200. Line counts are reported
with each work package.

## Scope and authority

- In scope: spec §4–§8, plus WP0 (see the [roadmap](roadmap.md)) if the owner agrees.
- Out of scope: spec §1 "do not implement"; docs pages (spec §7.4) unless the owner asks.
- Sandbox writes: only a rule with short code `RNCLIENT_PROBE` (Phase 0) or
  the integration test's own rule, in the dataset chosen in Q-02. No other
  rule, table or dataset is changed.
- Login tokens: the owner runs every live step in their own terminal. Copy the
  tokens just after a fresh login (lesson of 2026-11-12, see the
  schema-design [roadmap](../schema-design/roadmap.md)).

## Roles and permissions

- Owner: Marc Ridler. PM and worker: this Claude Code session. Independent
  reviewer: not yet assigned.
- Local edits, `uv sync`, tests: allowed.
- Commits use the owner's Git identity with no AI co-author line (R-04).

### Permission ledger

| Granted | Action | Scope | By | Until |
| --- | --- | --- | --- | --- |
| 2026-11-13 | Commit, one commit per work package, owner's Git identity, no AI co-author line | branch `feat/qc-rules` only; no push, no pull request, no merge | Marc Ridler (Q-05) | the owner withdraws it |
| 2026-11-13 | Rewrite the unpushed history of `feat/qc-rules` to redact server error details (internal host name, stack traces) from the probe records; fix the docs; extend the live test | branch `feat/qc-rules` only; no push | Marc Ridler ("Do those changes", after review) | used 2026-11-13 |
