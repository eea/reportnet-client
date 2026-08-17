from __future__ import annotations


class ReportnetError(Exception):
    pass


class APIError(ReportnetError):
    def __init__(self, status_code: int, response_body: str) -> None:
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"HTTP {status_code}: {response_body}")


class AuthError(APIError):
    pass


class RateLimitError(APIError):
    """Raised on HTTP 429 Too Many Requests."""
    pass


class DatasetLockedError(APIError):
    """Raised on HTTP 423 Locked — another job is already running on this dataset."""
    pass


class CodelistResolutionError(ReportnetError):
    """Raised when LINK/CODELIST fields could not be resolved to valid values.

    Only raised when ``strict=True`` is passed to
    :meth:`~reportnet.DataflowClient.get_codelists` or
    :meth:`~reportnet.DataflowClient.get_template`. By default, unresolved
    fields are logged and warned about, and the affected columns fall back to
    plain strings.

    Attributes:
        unresolved: Names of the fields that could not be resolved.
    """

    def __init__(self, unresolved: list[str], detail: str = "") -> None:
        self.unresolved = unresolved
        message = (
            f"Could not resolve valid values for {len(unresolved)} field(s): "
            f"{sorted(unresolved)}"
        )
        super().__init__(f"{message}. {detail}".strip())


class JobFailedError(ReportnetError):
    def __init__(self, job_id: int, status: str) -> None:
        self.job_id = job_id
        self.status = status
        super().__init__(f"Job {job_id} ended with status {status}")


class JobTimeoutError(ReportnetError):
    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        super().__init__(f"Timed out waiting for job {job_id}")
