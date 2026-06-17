from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from ._http import HttpSession
from .exceptions import JobFailedError, JobTimeoutError


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    REFUSED = "REFUSED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"
    FINISHED = "FINISHED"
    CANCELED_BY_ADMIN = "CANCELED_BY_ADMIN"

    @property
    def is_terminal(self) -> bool:
        return self not in (JobStatus.QUEUED, JobStatus.IN_PROGRESS)

    @property
    def is_successful(self) -> bool:
        return self == JobStatus.FINISHED


@dataclass
class JobHandle:
    job_id: int
    polling_url: str
    _http: HttpSession = field(repr=False)
    # Set only for etl_export handles; None for import/validation handles.
    _download_path: str | None = field(default=None, repr=False)

    def status(self) -> JobStatus:
        response = self._http.get(self.polling_url)
        return JobStatus(response.json()["status"])

    def wait(
        self,
        *,
        poll_interval: float = 5.0,
        timeout: float | None = None,
    ) -> "JobHandle":
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            current = self.status()
            if current.is_terminal:
                if not current.is_successful:
                    raise JobFailedError(self.job_id, current.value)
                return self
            if deadline is not None and time.monotonic() >= deadline:
                raise JobTimeoutError(self.job_id)
            time.sleep(poll_interval)

    def result(
        self,
        *,
        poll_interval: float = 5.0,
        timeout: float | None = None,
    ) -> bytes:
        if self._download_path is None:
            raise TypeError("result() is only valid on export handles returned by etl_export()")
        self.wait(poll_interval=poll_interval, timeout=timeout)
        # TODO: verify /orchestrator/jobs/download/{jobId} against the live API
        return self._http.get(self._download_path).content
