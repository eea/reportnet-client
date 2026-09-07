# Logging

The library logs to the `reportnet` logger and installs a `NullHandler`, so it
stays completely silent until your application opts in.

```python
import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger("reportnet").setLevel(logging.DEBUG)
```

## Levels

| Level | Content |
|---|---|
| `DEBUG` | Every HTTP request and response status; every job poll. Verbose by design. |
| `INFO` | Job status transitions with elapsed time, reference-dataset selection, codelist coverage. |
| `WARNING` | Retries (with reason and delay), failed or timed-out jobs, and **any fallback that weakens the result**. |

Anything that causes the library to return less
than requested — an unresolved codelist, a reference export that was
forbidden — is always at least a warning. See
[Dataset schema](schema.md#link-and-codelist-fields) for how to turn those into
errors with `strict=True`.

## Example

A typical export at `INFO`:

```
INFO reportnet.dataflow: selected reference dataset 108961
     (Reference Dataset - Spatial codelist), covering 10 LINK field(s)
INFO reportnet.dataflow: exporting reference dataset 108961 to resolve codelists
INFO reportnet.jobs: job 447821: IN_PROGRESS (after 0s)
INFO reportnet.jobs: job 447821: FINISHED (after 21s)
INFO reportnet.dataflow: codelists from reference dataset 108961:
     resolved 10/10 LINK/CODELIST field(s)
```

And a transient network failure at `WARNING`, which the client retries for you:

```
WARNING reportnet._http: GET /representative/v1/dataflow/2003 failed
        (The read operation timed out); retrying in 1.0s (attempt 1/3)
```

## Per-module loggers

Each module logs under its own name, so you can turn parts up or down:

| Logger | Covers |
|---|---|
| `reportnet._http` | requests, retries |
| `reportnet.jobs` | job polling and status transitions |
| `reportnet.dataflow` | orchestration: templates, codelists, imports |

```python
# Suppress per-request records, retain job progress
logging.getLogger("reportnet").setLevel(logging.DEBUG)
logging.getLogger("reportnet._http").setLevel(logging.WARNING)
```

## API keys

The key is sent as a header and no log record includes headers. A unit test
asserts this.
