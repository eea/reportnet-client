# Decisions: schema design for custodians

**For:** the project owner. **Status:** 2026-11-12.

## Quick answers

The PM's recommendation for each open question. Reply "agree" to accept them
all, or name the ones you would answer differently.

| # | Recommendation | Why |
| --- | --- | --- |
| D-01 | Treat the technical brief's sections 1, 2, 7, 8 and 9 as the approved success criteria | You said "implement accordingly"; the brief already states measurable targets |
| D-02 | One branch, `feat/schema-design`, with one commit per work package; you split it into pull requests later if you want | The brief asks for small PRs; per-package commits keep that option open without seven branches |
| D-03 | Refuse changes to a schema that already has a data collection or reporting datasets, unless the caller passes `allow_after_data_collection=True` | The brief says "warn or refuse"; behaviour after data collection was never tested. The check is per schema, so a new scratch dataset in a live dataflow such as 11468 is allowed |
| D-04 | Accept the change to one existing test, `test_connect_interactive_passes_sandbox_flag_to_keyring` | It pins the wrong sandbox host; keeping it would keep the bug |
| D-05 | You run the integration tests yourself, with a login token for sandbox 11468 | The agent has no token, and the test creates a dataset in a shared sandbox |
| D-06 | Do not add the field types "Multiline text", "Email", "URL", "Phone" yet | Their API names are guesses; unknown names already pass through unchanged |
| D-09 | Accept the size overrun (source ≈ 1,360 lines against 900; tests ≈ 1,035 against 700) | Most of it is docstrings and the in-memory fake that makes read-back testable; see the [roadmap](roadmap.md#size) |

| # | Question | Affects | Urgency |
| --- | --- | --- | --- |
| [D-01](#d-01) | Are the brief's criteria approved as the finish line? | everything | high |
| [D-02](#d-02) | One branch or seven pull requests? | commits | medium |
| [D-03](#d-03) | Warn or refuse after data collection? | `SchemaDesigner` | medium |
| [D-04](#d-04) | May one existing test change? | tests | medium |
| [D-05](#d-05) | Who runs the live tests? | S8 | medium |
| [D-06](#d-06) | Add unverified field types? | `FieldType` | low |

## Open

### D-01

**Are the technical brief's targets the finish line?** The library asks the
owner to approve success criteria before work starts (R-60). The brief's
criteria are in the [project brief](brief.md#success-criteria), S1–S9.
**Recommended:** approve as written.

### D-02

**How should the work be committed?** No commit is authorised yet (R-02).
**Options:** (1) one branch, one commit per package; (2) seven branches and
seven pull requests. **Recommended:** (1).

### D-03

**What happens to a schema change once data collections exist?** Not tested
(brief §10). **Options:** (1) refuse unless `allow_after_data_collection=True`;
(2) warn and continue. **Recommended:** (1). The check compares this design
dataset's schema id with `dataCollections` and `reportingDatasets` from
`GET /dataflow/v1/{id}`. It was first written per dataflow; on 2026-11-12 the
PM narrowed it to the schema, because the dataflow-wide check would have
refused every scratch dataset in sandbox 11468.

### D-04

**May an existing test change?** `tests/test_connect_interactive.py` expects
requests to `https://sandbox.reportnet.europa.eu`, the web-app host that
returns HTML (brief §2.2). **Recommended:** change the expected host to
`https://sandbox-api.reportnet.europa.eu`. No other existing test changes.

### D-05

**Who runs the live tests?** They need `RN3_SANDBOX_ACCESS_TOKEN` and
`RN3_SANDBOX_REFRESH_TOKEN`, and they create a design dataset named
`rnclient-it-<timestamp>` in sandbox dataflow 11468 that cannot yet be deleted
by the API (brief §10). **Recommended:** the owner runs
`uv run pytest --integration -m integration -k schema_design -v` and deletes
the dataset in the web app afterwards.

### D-06

**Add the four unverified field types?** **Recommended:** no, until one live
create-and-read shows their names (brief §10).

## Settled by the evidence, waiting for confirmation

- **D-07, where the work happens.** The main checkout holds about 2,000
  uncommitted lines on `fix/validation-evidence` in the same files. The work
  is done in a separate worktree, `.claude/worktrees/schema-design`, on
  `feat/schema-design` from `main` (b10da6e), so neither piece of work is mixed
  into the other. Merging the two later may need conflict resolution in
  `client.py`, `models.py`, `dataflow.py` and `CHANGELOG.md`.
- **D-08, `AGENTS.md`.** The brief (§9) is right that the repository has no
  `AGENTS.md`: `.gitignore` line 41 ignores it on purpose, so it exists only
  in the owner's local checkout. This project does not add it to Git. The
  local copy still names the old sandbox host
  (`https://sandbox.reportnet.europa.eu`); the owner should change it to
  `https://sandbox-api.reportnet.europa.eu`. Alternative: track the file, as
  `CONTRIBUTING.md` implies.

## Settled

- **D-10.** Commit the work on `feat/schema-design`, one commit per work
  package, under the owner's Git identity with no AI co-author line (R-04),
  then push the branch to `origin`. No pull request, no merge. (Marc Ridler,
  2026-11-12.)
- **D-11.** The live tests run on the common workspace (CWS), which can reach
  the sandbox, in a new session. The laptop cannot: neither sandbox host
  resolves in DNS there. The PM writes the instructions for that session:
  [cws-test-instructions.md](cws-test-instructions.md). This replaces the
  recommendation in D-05 that the owner runs the tests on the laptop. (Marc
  Ridler, 2026-11-12.)
