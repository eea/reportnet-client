# Project brief: schema design for custodians

**For:** the owner, the PM and any agent resuming this work. **Status:**
2026-11-12. **Follows:** `eea/ai-reporting-workflows` at commit `main` as
cloned on 2026-11-12 (no release tag yet). **Source:**
`temp/AGENT_BRIEF_schema_design.md` in the main checkout (the owner's technical
brief; sections are cited below as "brief §n").

## Workflow

None of the four library workflows fits a code library exactly. This project
uses the library's general rules (roles, permissions, evidence, operations,
reviewability, success criteria) and the repository's own `AGENTS.md`, which
takes precedence over the library's SHOULD rules.

## Objective

Let a custodian create and change **design dataset schemas** from Python:
create an empty dataset schema, rename it, set its description, add, change,
move and delete tables and fields, and export a table definition as CSV.
Completion means the code, unit tests, integration tests, docs and notes
below, on branch `feat/schema-design`, reviewed and ready for the owner to
open a pull request.

Readers: custodians (secondary users of the library, see `AGENTS.md`). Docs
stay plain and task-shaped (`CONTRIBUTING.md`).

## Success criteria

Taken from the owner's technical brief (§1, §2, §7, §8, §9) on 2026-11-12. The
owner's instruction "implement accordingly" is recorded as approval; see
[D-01](decisions.md#d-01).

| # | Criterion | Measure | Target | Evidence | Who checks |
| --- | --- | --- | --- | --- | --- |
| S1 | Existing behaviour kept | unit tests that passed on `main` (b10da6e) | 300 of 300 still pass; only the one test that pins the wrong sandbox URL is changed ([D-04](decisions.md#d-04)) | `uv run pytest` | PM |
| S2 | Sandbox URL fixed | `SANDBOX_URL` value | `https://sandbox-api.reportnet.europa.eu`, pinned by a test | unit test | PM |
| S3 | `fieldSchema: null` parses | `TableSchema.from_dict` with null field list | no error, 0 fields | unit test | PM |
| S4 | Login-token authentication | bearer header; refresh before expiry; one refresh and resend on 401; rotated refresh token kept; no secret in logs | each behaviour has a unit test | `tests/test_token_auth.py` | PM |
| S5 | Every endpoint in brief §3.1–3.3 wrapped | one `ReportnetClient` method per endpoint, request shape as captured | one unit test per method | `tests/test_schema_design.py` | PM |
| S6 | Safety rules of brief §7 | API key refused before any request; table with data refused unless `force=True`; non-design dataset refused; duplicate names refused; full-body field PUT; read-back after each write | one unit test per rule | `tests/test_schema_design.py` | PM |
| S7 | Static checks | `ruff check src tests`, `mypy src` (strict) | 0 errors | command output | PM |
| S8 | Live cycle on sandbox 11468 | integration test of brief §8.2 | passes on the CWS, or each failure recorded with its cause | `tests/test_schema_design_integration.py`; CWS report ([instructions](cws-test-instructions.md)) | owner |
| S9 | Docs and notes | custodians guide, api notes, changelog, API pages, mkdocs nav | written; `mkdocs build --strict` passes | files | PM, owner |

Passing these is not acceptance (R-64). The owner accepts the exact commit.

## Size budget

About 1,500 new lines in total: `src` ≤ 900, tests ≤ 700, docs and notes
≤ 300. Line counts are reported with each work package.

## Scope and authority

- In scope: brief §1 goal, §2 fixes, §3 endpoints, §4 token auth, §5 model
  changes, §7 safety rules, §8 tests, §9 docs.
- Out of scope (brief §10, not verified): deleting a whole design dataset,
  importing a table definition, whole-schema export/import/copy, dataset
  flags, unique and row constraints, webforms, new field types.
- Writable: the worktree `.claude/worktrees/schema-design` (branch
  `feat/schema-design`, from `main` b10da6e). Read-only: the main checkout and
  its uncommitted work on `fix/validation-evidence`.
- No live API calls by the agent: the agent has no login token, and writes to
  the shared sandbox need the owner's permission ([D-05](decisions.md#d-05)).

## Roles and permissions

- Owner: Marc Ridler. PM and worker: this Claude Code session (no separate
  worker session was asked for, so the PM builds each package and reviews it
  before starting the next). Independent reviewer: not yet assigned.
- Local edits, `uv sync`, tests: allowed in the worktree.
- Commit and push: authorised once, see the ledger. Pull request and merge:
  **not authorised**. Commits use the owner's Git identity with no AI
  co-author line (R-04). The session on the CWS has no commit or push
  permission unless the owner grants it there.

### Permission ledger

| Granted | Action | Scope | By | Until |
| --- | --- | --- | --- | --- |
| 2026-11-12 | Commit, one commit per work package, owner's Git identity, no AI co-author line | branch `feat/schema-design` only | Marc Ridler | the push below |
| 2026-11-12 | Push | `feat/schema-design` to `origin` (github.com/eea/reportnet-client); no pull request, no merge, no force push | Marc Ridler | done once |

## Environment

uv, Python and the lockfile from the repository (`uv sync`). No new
dependencies.
