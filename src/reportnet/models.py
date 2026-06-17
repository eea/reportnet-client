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
    # True only for etl_export handles; guards result() usage.
    _is_export: bool = field(default=False, repr=False)
    # Populated from the poll response once the job reaches FINISHED.
    # Live API returns: {"status": "FINISHED", "downloadUrl": "/orchestrator/jobs/downloadEtlExportedFile/{jobId}?..."}
    _download_url: str | None = field(default=None, repr=False)

    def _poll(self) -> dict[str, object]:
        data: dict[str, object] = self._http.get(self.polling_url).json()
        if url := data.get("downloadUrl"):
            self._download_url = str(url)
        return data

    def status(self) -> JobStatus:
        return JobStatus(self._poll()["status"])

    def wait(
        self,
        *,
        poll_interval: float = 5.0,
        timeout: float | None = None,
    ) -> "JobHandle":
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            data = self._poll()
            current = JobStatus(data["status"])
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
        if not self._is_export:
            raise TypeError("result() is only valid on export handles returned by etl_export()")
        self.wait(poll_interval=poll_interval, timeout=timeout)
        if self._download_url is None:
            raise RuntimeError("Export FINISHED but poll response contained no downloadUrl")
        return self._http.get(self._download_url).content
