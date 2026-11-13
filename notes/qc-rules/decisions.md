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
