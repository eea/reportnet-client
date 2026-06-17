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


class JobFailedError(ReportnetError):
    def __init__(self, job_id: int, status: str) -> None:
        self.job_id = job_id
        self.status = status
        super().__init__(f"Job {job_id} ended with status {status}")


class JobTimeoutError(ReportnetError):
    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        super().__init__(f"Timed out waiting for job {job_id}")
