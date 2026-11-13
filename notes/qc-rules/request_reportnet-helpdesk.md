# Request to the Reportnet 3 helpdesk (draft, not sent)

**For:** the Reportnet 3 helpdesk or development team. **Status:** draft
prepared 2026-11-13 for the owner to check and send. **Related decisions:**
[D-06, D-07](decisions.md).

**Before sending, the owner confirms:**
- the recipient (helpdesk address or ticket system);
- that sandbox dataflow 11468 and datasets 48100 and 33796 may be named;
- whether to mention the Python client, or to describe only the API calls.

> **Subject:** Reportnet 3 sandbox, QC rules: invalid SQL marked "verified", and runSqlRule fails on a column named "Group"
>
> Dear colleagues,
>
> We are building a Python client for the Reportnet 3 REST API that lets
> custodians manage SQL QC rules on design datasets. We test it on sandbox
> dataflow 11468 with a login token. We found two things we cannot explain,
> and one question.
>
> **A. Invalid SQL is marked as verified**
>
> On 13 November 2026 we created two SQL rules in design dataset 48100 with
> `PUT /rules/createNewRule`:
> - one with a syntax error: `SELECT * FROM dataset_48100."sites" WHERE`
> - one reading a table that does not exist: `SELECT * FROM dataset_48100."no_such_table"`
>
> Both were accepted. After `POST /rules/validateSqlRules`, both showed
> `verified: true` and `sqlError: null` in `GET /rules/{schemaId}/dataflow/11468`.
> `POST /rules/evaluateSqlRule` answered `0.0` for both, as it does for valid
> SQL.
>
> 1. Is there an API call that reports whether a rule's SQL is valid, as the
>    web app's rule editor does?
> 2. What do `verified` and `sqlError` mean after `validateSqlRules`, and when
>    are they final? Straight after the call they were still `null`.
>
> **B. runSqlRule fails on a dataset with a column named "Group"**
>
> `POST /rules/runSqlRule?datasetId=33796&showInternalFields=false` with
> `SELECT * FROM dataset_33796."categories"` answered HTTP 500. The message
> shows that the server prefixes the query with one CTE per table, with column
> names unquoted:
>
> `WITH Categories AS (SELECT Group,Depth,Code,Description FROM Categories), … SELECT * FROM (SELECT * FROM "categories") as userSelect LIMIT 10 OFFSET 0`
>
> Dremio then fails with `PARSE ERROR: Encountered "Group"`, because `Group` is
> a reserved word. Quoting the column names in the generated CTEs would
> probably fix it.
>
> 3. Can you confirm this, and say whether the web app's "Run SQL" button is
>    affected in the same way?
>
> **C. One question**
>
> 4. `DELETE /rules/deleteRule` worked with the numeric dataset id in
>    `datasetId`, while the web app's code seems to send the schema id there.
>    Which one is intended?
>
> Until we hear from you, our client checks rule SQL only on its own side
> (the SQL must start with SELECT or WITH), and says in its documentation that
> Reportnet does not check it.
>
> Kind regards,

**Evidence:** `notes/live-tests-qc-11468.json` (part 1: `evaluateSqlRule`,
`deleteRule`) and `notes/live-tests-qc-11468-part2.json` (part 2: the invalid
rules after "validate all", and `runSqlRule` on 33796), both recorded on
2026-11-13; summary in `notes/api-notes.md`, section "QC rules".
