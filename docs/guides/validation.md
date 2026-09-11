# Checking your data

Validation runs Reportnet's own quality rules on the server and tells you what
is wrong.

```python
result = me.validate(dataset_id=108952, timeout=1800)
print(result.summary())
```

```
dataset 108952: 8 issue(s) — 3 BLOCKER, 4 ERROR, 1 WARNING
```

## It is slow

Minutes, not seconds. A large dataflow can take **twenty minutes or more** — one
dataset here runs 433 rules. `validate()` waits for it, so give it a generous
`timeout`.

If it times out, the run is still going. **Do not start another one.** Reportnet
refuses a second validation and puts an error banner on your dataflow. Read the
results instead, which starts nothing:

```python
result = me.get_validation_results(dataset_id=108952)
```

## Make sure you are reading this run

Reportnet's results carry no timestamp and no run number. While a new validation
is going, it keeps serving the *previous* run's results — so old numbers look
exactly like new ones. Identical totals from changed data is the whole trap.

So always check:

```python
if result.is_stale:
    print("These are from an older run — wait and read again.")
```

`is_stale` is true when a validation is still running, or when you uploaded data
after the last run finished. If you want the detail:

```python
print(result.job.id, result.job.status_changed_at)   # which run these came from
print(result.data_changed_at)                        # when data last changed
print(result.superseded_by)                          # a run happening now
```

## Reading the issues

```python
for issue in result.issues:
    print(issue.level, issue.table, issue.field, issue.record_count, issue.message)
```

```
BLOCKER Reporter      None 1  Mandatory table has no records
ERROR   DischargePoints dcpState 15  The value is not a valid member of the referenced list.
WARNING UWWTPs        None 14  Some of the treatment plants reported as PASSED are potentially overloaded
```

Or as a table:

```python
print(result.to_frame())
```

## What the levels mean

| Level | Meaning |
|---|---|
| **BLOCKER** | must be fixed — you cannot release |
| **ERROR** | should be fixed |
| **WARNING** | looks odd; often fine, but worth a look |
| **INFO** | for your information |

```python
if result.has_blockers:
    print("Not ready to release yet.")
```

## A failing rule is a question, not a verdict

Rules are written by the dataflow's administrators, and they can be wrong. One
real example: a rule reported *"plants with capacity over 100 000 p.e. are
missing an E-PRTR code"* and flagged all fifteen plants in a dataset where only
one was that large — its SQL was missing a pair of brackets.

If a rule fires on data you believe is correct, read the message carefully and
ask the dataflow's custodian. Do not contort good data to satisfy a bad rule.

## Next

[Downloading](export.md), or [when something goes wrong](troubleshooting.md).
