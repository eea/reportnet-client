# Exceptions

All exceptions inherit from [`ReportnetError`][reportnet.ReportnetError].

```
ReportnetError
  APIError(status_code, response_body)
    AuthError          # 401 / 403
    DatasetLockedError # 423 — another job is already running
    RateLimitError     # 429
  JobFailedError(job_id, status)   # job ended in a non-FINISHED terminal state
  JobTimeoutError(job_id)          # wait() exceeded its timeout
```

::: reportnet.ReportnetError

::: reportnet.APIError

::: reportnet.AuthError

::: reportnet.DatasetLockedError

::: reportnet.RateLimitError

::: reportnet.JobFailedError

::: reportnet.JobTimeoutError
