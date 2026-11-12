# Exceptions

All exceptions inherit from [`ReportnetError`][reportnet.ReportnetError].

```
ReportnetError
  APIError(status_code, response_body)
    AuthError          # 401 / 403
      SchemaDesignNotPermittedError  # schema change tried with an API key
    SchemaWriteUncertainError  # 5xx on a schema change; it may still have been applied
    DatasetLockedError # 423 — another job is already running
    RateLimitError     # 429
  JobFailedError(job_id, status)   # job ended in a non-FINISHED terminal state
  JobTimeoutError(job_id)          # wait() exceeded its timeout
  CodelistResolutionError(unresolved)      # only when strict=True
  ExportVerificationError(verification)    # export did not match the schema
  ReadbackVerificationError(verification)  # upload did not match the readback
  SchemaDesignError                # a schema change refused by the client's own checks
    TableHasDataError              # the table holds records (override: force=True)
    DuplicateNameError             # a table or field name already in use
    SchemaReadbackError            # accepted, but the schema read back differs
```

::: reportnet.ReportnetError

::: reportnet.APIError

::: reportnet.AuthError

::: reportnet.DiscoveryNotPermittedError

::: reportnet.DatasetLockedError

::: reportnet.RateLimitError

::: reportnet.JobFailedError

::: reportnet.JobTimeoutError

::: reportnet.CodelistResolutionError

::: reportnet.ExportVerificationError

::: reportnet.ReadbackVerificationError

::: reportnet.SchemaDesignNotPermittedError

::: reportnet.SchemaWriteUncertainError

::: reportnet.SchemaDesignError

::: reportnet.TableHasDataError

::: reportnet.DuplicateNameError

::: reportnet.SchemaReadbackError
