# Live test report: schema design on sandbox dataflow 11468

**For:** the owner and the PM. **Date:** 2026-11-12. **Instructions:**
[cws-test-instructions.md](cws-test-instructions.md).

## Outcome

**Passed.** `test_schema_design_full_cycle` passed against the real Reportnet
sandbox. Commit tested: `7726eebc5c92cb68d6ca65de521edd0f27053e74`
(`feat/schema-design`).

## Where and how it ran: a change from the instructions

The test did not run on the CWS. On 2026-11-12 the sandbox API host answered
`401` from the owner's laptop (now on the VPN), so it ran there. This changes D-11.

- The PM session ran steps 1 and 2.
- The owner ran steps 3 and 4 in their own terminal, because the tokens had to
  stay out of the agent session. The tokens went from the web app's session
  storage to the clipboard and into environment variables, so they were never
  shown or saved.
- Output went to two log files outside the repository. The PM scanned both for
  token-like strings (0 matches) before reading them.

## Steps

| Step | Result |
| --- | --- |
| 1a. Inputs | HEAD `7726eeb`. The tree was clean except for two PM edits to the notes (`brief.md`, `roadmap.md`); no code changed |
| 1b. Reachability | `401` without credentials |
| 2. Offline checks | 370 passed, 63 skipped; `ruff` all checks passed; `mypy` no issues in 18 source files; `uv.lock` unchanged |
| 3. Read-only preflight | `bigData: True`; design datasets 48099, 48097, 48096, 33796, 33797; 0 data collections, 0 reporting datasets; `validate_schemas` True |
| 4. Live cycle | `test_schema_design_full_cycle` **passed** (16.65 s for the run); `test_api_key_is_refused_schema_reads` skipped, because no sandbox API key is in the keyring |

**Scratch dataset:** 48100 `rnclient-it-20261112-152744`, schema
`6af5cce0c6dc4400014d1f72`. All of its tables and fields were deleted at the
end of the test; the empty dataset itself remains.

## Known risks

| # | Question | Answer |
| --- | --- | --- |
| 6a | Did the LINK field update succeed? | **Yes.** The PUT carrying `referencedField` as read from GET was accepted, and the read-back kept the link to `SiteCode`. Limit: the test does not assert that the new description was stored |
| 6b | Was a token renewal needed? | **Not known.** Step 3 printed "valid for None min": the client could not read an expiry from the access token, so it cannot renew the token ahead of time and relies on renewing after a 401. The message "refreshing the Reportnet login token" is logged at INFO level to a silent handler, so `-s` would not have shown it. The run took about 17 s, a few minutes after the token was copied, so a renewal is unlikely. Renewal against the real server is still untested |
| 6c | Automatic rules after the build | 7 |

## Other findings

- Design dataset 48099 `IMPORTED_ClaudeImportTest` exists in 11468 but is not
  in the instructions' do-not-touch list. The test did not touch it.
- The library's step 6b check was flawed: `-s` cannot show a log line
  that goes to a `NullHandler`. Next time, run with
  `--log-cli-level=INFO`.

## Acceptance criteria

| Criterion | Met |
| --- | --- |
| Step 2 counts match | yes (on the laptop, not the CWS) |
| Full cycle passes against the real sandbox | yes |
| No other dataset changed | yes, as far as the code shows: every write in the test goes to dataset 48100 or its schema. Not checked independently in the web app |
| No token in any file, log or message | yes: 0 token-like matches in both logs; no token was shown in this session |
| No change under `src/` or `tests/` | yes: `git status` shows only notes |

## Decisions for the owner

- Delete scratch dataset 48100 `rnclient-it-20261112-152744` in the web app:
  **yes**.
