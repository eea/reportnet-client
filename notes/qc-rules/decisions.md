# Decisions: SQL QC rule editing

**For:** the project owner. **Status:** 2026-11-13.

## Quick answers

Reply "agree" to accept all of the PM's recommendations, or name the ones you
would answer differently.

| # | Question | Recommendation | Why |
| --- | --- | --- | --- |
| Q-01 | Approve the success criteria Q1–Q9 in the [brief](brief.md)? | Yes | They are spec §9 plus three checks the spec implies: Python 3.10, a clean sandbox, no secrets |
| Q-02 | Which dataset does the probe use? | **48099 only if it is yours and has a `sites` table**; otherwise scratch dataset 48100, with a `Sites` table added first | Yesterday's D-12 proposed adding 48099 to the do-not-touch list. Dataset 48100 is already scratch, so its deletion (D-12) would wait until this project ends |
| Q-03 | Fix the misleading token error first (WP0)? | Yes | Without the fix, every token problem during the probe reads as "reporter keys must be scoped", which cost several runs yesterday |
| Q-04 | Probe step 7, a write with an API key: run it? | Only if a sandbox API key is already in your keyring; otherwise skip it and mark it "not verified" | Not worth creating a key: `createApiKey` replaces your existing one |
| Q-05 | Commit permission | One commit per work package on `feat/qc-rules`, your Git identity, no AI co-author line; push only when you say so; no pull request | The same arrangement as the schema-design project |
| Q-06 | Mark WP0–WP1 *ready* | Yes | Both are offline. WP2 needs you and a fresh login |

## Settled

- **2026-11-13, owner: "Follow the recommendations."** Q-01 to Q-06 are
  accepted as recommended:
  - Q-01: the success criteria Q1–Q9 are approved.
  - Q-02: whether 48099 belongs to the owner was not confirmed, so the probe
    defaults to scratch dataset **48100**, with a `Sites` table added. The
    deletion of 48100 (schema-design D-12) waits until this project ends.
    `DATASET_ID` is one parameter, so the owner can switch it to 48099.
  - Q-03: WP0 goes first.
  - Q-04: step 7 runs only if a sandbox API key is already in the keyring.
  - Q-05: commit permission as stated; see the brief's ledger.
  - Q-06: WP0 and WP1 are ready.

## Answered 2026-11-13 ("agree"): Q-10, Q-11 and Q-12 as recommended

- Q-10: D-06 is accepted, so the designer checks SQL client-side only.
- Q-11: WP5 and WP6 are ready.
- Q-12: the PM drafts a note to the Reportnet helpdesk about the two API
  problems and does not send it (R-46).

## Answered 2026-11-13 ("agree"): Q-07, Q-08 and Q-09 as recommended

WP2b and WP3 are ready. The validate-after-write design of Q-07 is used once
WP2b confirms what an invalid rule looks like.

## Asked after the Phase 0 probe (2026-11-13)

| # | Question | Recommendation | Why |
| --- | --- | --- | --- |
| Q-07 | `evaluateSqlRule` returns `0.0` for invalid SQL too, so the `check_sql` guard of spec §7.3 cannot work. What replaces it? | `add_sql_rule(..., validate=True)`: after the write, call "validate all", read the rule back and raise `QcSqlError` with its `sqlError` if it is not verified. The rule stays in place, and the error says so. `evaluate_sql_rule` stays as a raw method that returns the cost | "Validate all" is the only call seen to change `verified`. It also re-checks the dataset's other rules, which is what the web app's validate button does |
| Q-08 | Run a second small probe (WP2b) before relying on Q-07? | Yes, on 48100: create a rule with invalid SQL, validate all, record `verified` and `sqlError`, delete it. In the same run, test-run SQL **read-only** on a dataset that holds data (33796 "Reference data", `LIMIT 10`, no writes), with the table name in both cases | Q-07 assumes what an invalid rule looks like, and the test-run result was not conclusive |
| Q-09 | Start WP3 (models and raw client methods) now? | Yes | Offline; nothing in WP3 depends on the open points |

## Settled by the evidence

- **D-01, `Severity` is `(str, Enum)`, not `StrEnum`.** `pyproject.toml`
  declares `requires-python = ">=3.10"`, and `StrEnum` needs 3.11. This
  follows the existing `FieldType` pattern. It differs from spec §7.1 only in
  the base class; the values are the same.
- **D-02, the spec's base is current.** `18185dd` is the merge of PR #20
  (`feat/schema-design`) into `main`. Every internal name the spec reuses
  exists there: `_schema_write`, `_require_login_token`,
  `SchemaDesignNotPermittedError`, `SchemaDesignError`, `DuplicateNameError`,
  `SchemaReadbackError`, `SchemaWriteUncertainError`,
  `public_schema._SQL_START` and `get_dataset_metabase`.
- **D-03, `deleteRule` takes the dataset id.** The probe found that the schema
  id gives 400 and the numeric dataset id works, so spec §4 note 2 is wrong.
  `delete_rule` sends `datasetId={dataset_id}`.
- **D-06, the API cannot check SQL; replaces Q-07 (WP2b, 2026-11-13).** Two
  rules with invalid SQL were accepted, and "validate all" marked them
  `verified: true` with no `sqlError`. `QcDesigner` therefore guards only
  client-side (SQL starts with `SELECT` or `WITH`, a valid severity, a unique
  short code). Its documentation says that Reportnet does not check the SQL.
  There is no `check_sql` and no `validate=True`; `validate_all()` stays as a
  documented pass-through. The owner may still object; nothing else was
  possible.
- **D-07, `runSqlRule` stays wrapped but not verified.** On 33796 it fails
  because of Reportnet's own query wrapper (an unquoted reserved-word column,
  `Group`). `QcDesigner.test_sql()` passes the call through, and its
  documentation names this limit.
- **D-05, `to_body()` sends the web app's keys only.** Spec §7.1 says to keep
  unknown keys from `raw`. The probe verified only the web app's body
  (spec §5), and GET adds `salience`, `hasHistoric`, `referenceFieldSchemaPKId`
  and `whenConditionMethod`, which were never sent on a write. Sending only
  the verified body is the safer choice; the schema-design project left the
  same question open for LINK fields.
- **D-04, create returns no id.** As spec §5 expected, the new rule is found
  by its `shortCode`.
