# Exceptions

All exceptions inherit from [`ReportnetError`][reportnet.ReportnetError].

```
ReportnetError
  APIError(status_code, response_body)
    AuthError          # 401 / 403
      LoginTokenError                # a login token could not be issued or renewed
      SchemaDesignNotPermittedError  # schema or QC rule change tried with an API key
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
    DuplicateNameError             # a table, field name or rule short code already in use
    SchemaReadbackError            # accepted, but the schema or rule read back differs
    QcRuleNotEditableError         # an automatic or non-SQL rule; change it in the web app
    QcSqlError                     # rule SQL refused by the client's own check
```

::: reportnet.ReportnetError

::: reportnet.APIError

::: reportnet.AuthError

::: reportnet.LoginTokenError

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

::: reportnet.QcRuleNotEditableError

::: reportnet.QcSqlError
