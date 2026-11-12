# CWS test: schema design on the Reportnet sandbox

**For:** the agent or person running the live tests on the common workspace
(CWS). **Written:** 2026-11-12 by the PM session that built the code.
**Applies to:** branch `feat/schema-design` of `eea/reportnet-client`.

Copy the block below into a new session on the CWS. It stands alone.

---

```text
Live test only: run the schema-design checks on Reportnet sandbox dataflow 11468 and report; change no code.

From the PM of the "schema design for custodians" work (a Claude Code session on
the owner's laptop, which cannot reach the sandbox). The two sessions cannot
message each other. Put your full report in your own window for the owner AND
in the file named under "Deliver"; the owner carries it back.

WHO AND WHAT
- Owner: Marc Ridler. Reportnet custodian of sandbox dataflow 11468
  ("SANDBOX - Approximated greenhouse gas inventories - [Reporting 2025]",
  a BigData dataflow).
- Repository: https://github.com/eea/reportnet-client, branch
  feat/schema-design. Rules for agents in this library: AGENTS.md is NOT in
  Git (it is in .gitignore); read CONTRIBUTING.md instead. Project rules:
  https://github.com/eea/ai-reporting-workflows (AGENTS.md, roles/worker.md).
- Read first, in the repository: notes/schema-design/brief.md,
  notes/schema-design/roadmap.md, notes/schema-design/decisions.md, and the
  section "Schema design (sandbox, dataflow 11468, 2026-11-12)" at the end of
  notes/api-notes.md.

CONTEXT (already checked; re-check what step 1 says)
- The new code lets a custodian change design dataset schemas from Python:
  ReportnetClient.from_tokens(), DataflowClient.create_design_dataset(),
  DataflowClient.design() -> SchemaDesigner.
- API keys get 403 on schema writes; a LOGIN TOKEN (Keycloak bearer) is needed.
- The sandbox API host is https://sandbox-api.reportnet.europa.eu. It is
  reachable only from inside the EEA network/VPN. On the owner's laptop
  neither sandbox host resolved in DNS on 2026-11-12.
- On the laptop: 370 unit tests passed, 63 skipped; ruff and mypy clean.
- Everything was built against an in-memory fake. Nothing has run against the
  real sandbox yet. That is what this test is for.

OWNER DECISIONS THAT APPLY (2026-11-12)
1. Commit and push of feat/schema-design were authorised for the PM session on
   the laptop only. You are NOT authorised to commit, push, open a pull
   request or merge, unless the owner says so in your session, for that exact
   action.
2. The live test creates one design dataset named rnclient-it-<timestamp> in
   dataflow 11468. There is no verified API call to delete it; the owner
   deletes it in the web app afterwards.

AUTHORISED SCOPE
- Clone or fetch the repository, run uv sync and the commands below, and write
  one report file.
- Reportnet writes are allowed ONLY inside the new rnclient-it-* dataset that
  the test creates.
Out of scope:
- Editing any file under src/ or tests/. If something fails, report it; do not fix it.
- Design datasets 33796 "Reference data" (holds data) and 33797 "Reporting data",
  48096 "NewSchemaForClaude" (the owner's), 48097 "ClaudeApiTestRenamed",
  and anything outside dataflow 11468. Do not change them in any way.
- Calling /user/createApiKey (it replaces the owner's API key).

SECRETS
- The owner sets the tokens in your terminal as environment variables
  RN3_SANDBOX_ACCESS_TOKEN and RN3_SANDBOX_REFRESH_TOKEN. They copy them from
  the sandbox web app while logged in: DevTools -> Application -> Session
  storage -> reportnet_03 -> accessToken / refreshToken.
- Never ask the owner to paste a token into the chat. Never print, log, save or
  commit a token, including in the report. If a token appears in any output,
  stop and tell the owner to log out of the web app (that ends the session).
- The refresh token rotates when the client renews it. Afterwards the owner's
  browser session may need a fresh login. This is expected.

ENVIRONMENT
- Python 3.10-3.13 and uv. Use only `uv sync` and `uv run ...` in the
  repository folder. No global installs. Report if uv.lock changes.
- These are light commands. Stop and report if any single command runs for more
  than 15 minutes.

STEPS
1. Re-verify the inputs. Stop if anything differs.
   a. git clone https://github.com/eea/reportnet-client.git  (or git fetch)
      git checkout feat/schema-design && git pull --ff-only
      git status            -> clean
      git log --oneline -1  -> the commit that adds
                               notes/schema-design/cws-test-instructions.md
      Record the full commit id (git rev-parse HEAD).
   b. Sandbox reachable, no credentials sent:
      curl -s -o /dev/null -w "%{http_code}\n" https://sandbox-api.reportnet.europa.eu/dataflow/v1/11468
      Expect 401 or 403. "000" means it cannot be reached: stop.
2. Offline checks:
      uv sync
      uv run pytest -q              -> expect 370 passed, 63 skipped
      uv run ruff check src tests   -> All checks passed
      uv run mypy src               -> no issues
   Stop if the counts differ.
3. Read-only preflight with the login token. This changes nothing. Run:
uv run python - <<'PY'
import os, time, reportnet
from reportnet._auth import jwt_expiry
c = reportnet.ReportnetClient.from_tokens(
    os.environ["RN3_SANDBOX_ACCESS_TOKEN"],
    os.environ["RN3_SANDBOX_REFRESH_TOKEN"], sandbox=True)
exp = jwt_expiry(c.tokens.access_token)
print("access token valid for", None if exp is None else round((exp - time.time()) / 60), "min")
flow = c.for_dataflow(11468)
k = flow.get_dataflow_contents()
print("dataflow:", k.info.name, "| bigData:", k.info.big_data)
print("design datasets:", [(d.id, d.name) for d in k.design_datasets])
print("data collections:", len(k.data_collections), "| reporting datasets:", len(k.reporting_datasets))
print("schemas valid:", c.validate_schemas(dataflow_id=11468))
PY
   Expect bigData True and design datasets including 33796 and 33797.
   Stop on a 401/403, or if a token is printed.
4. The live cycle (writes, only in a new rnclient-it-* dataset):
      uv run pytest --integration -m integration -k schema_design -v -s
   It creates the dataset; adds tables Sites and Measurements; adds fields
   SiteCode (TEXT, primary key), Area (NUMBER_DECIMAL), Status (CODELIST
   open/closed) and Site (LINK to SiteCode); updates the LINK field and the Area
   description; reorders fields and tables; exports the Sites definition as CSV
   and compares it; then deletes the fields and tables. It prints the new
   dataset's id and name: record them.
   test_api_key_is_refused_schema_reads skips unless a sandbox API key is in
   the keyring (reportnet.save_key(11468, key, sandbox=True)). If the owner has
   one stored, let it run: it is read-only.
5. If the cycle fails part-way:
   - Copy the exception type and message exactly. SchemaWriteUncertainError
     means the change may still have been applied.
   - Do not re-run blindly. First read the scratch dataset's schema:
       uv run python -c "import os, reportnet; c = reportnet.ReportnetClient.from_tokens(os.environ['RN3_SANDBOX_ACCESS_TOKEN'], os.environ['RN3_SANDBOX_REFRESH_TOKEN'], sandbox=True); print(c.get_schema(dataset_id=<ID>))"
     and record what it holds.
   - A re-run creates a second scratch dataset. Re-run at most once, and only
     if the failure was "Load balancer does not have available server" (a
     known outage of about 30 seconds). Wait 2 minutes first.
6. Known risks to report on explicitly (yes / no / not reached):
   a. Did updating the LINK field ("link to Sites") succeed? It sends
      referencedField back with the extra keys that GET returns. This body was
      never captured from the web app.
   b. Did any request need a token refresh (look for "refreshing the Reportnet
      login token" with -s, or a changed token lifetime)? What lifetime did
      step 3 print?
   c. How many automatic rules did the run print?

DELIVER
1. notes/schema-design/cws-test-report-<YYYY-MM-DD>.md in the repository
   folder. Do not commit it unless the owner authorises that in your session.
   Contents: commit id tested; output summary of steps 1-4 (pass/fail counts,
   no tokens); scratch dataset id and name; answers to 6a-6c; every failure
   with its exact exception and the schema state read in step 5.
2. The same report in your window, leading with the outcome.

ACCEPTANCE CRITERIA
- Step 2 counts match (370 passed, 63 skipped) on the CWS.
- test_schema_design_full_cycle passes against the real sandbox, or its failure
  is recorded with the exact exception and the dataset's state afterwards.
- No dataset other than the new rnclient-it-* one was changed.
- No token appears in any file, log or message.
- No file under src/ or tests/ changed (git status shows only the report).

STOP CONDITIONS (stop and report; do not work around)
- The sandbox cannot be reached, or the branch or commit differs from step 1.
- Unit-test counts differ from step 2.
- 401/403 with the login token (the token may have expired: ask the owner to
  copy fresh ones).
- Any code change would be needed to continue.
- Any sign that a dataset other than the scratch one was touched.
- A token appears in output.

REPORT BACK, leading with the outcome:
1. Outcome: passed / failed at step N / stopped at step N, and why. Commit id tested.
2. Acceptance evidence.
3. Checks actually run, and anything taken on trust.
4. Changed files (should be only the report) and its line count.
5. Decisions only the owner can make, each with a recommendation.
   Always include: "Delete scratch dataset <id> <name> in the web app: yes."
6. The next ready task.
```
