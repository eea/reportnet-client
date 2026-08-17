"""Asynchronous job handling.

Most long-running operations in Reportnet (imports, exports, validations) are
asynchronous: the API returns a job ID and a polling URL, and the caller polls
until the job reaches a terminal status.  :class:`JobHandle` wraps that loop.

``JobHandle`` is a *service* object, not a data model — it holds a live HTTP
session and performs network I/O — which is why it lives here rather than in
:mod:`reportnet.models`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from ._http import HttpSession
from ._log import get_logger
from .exceptions import JobFailedError, JobTimeoutError

logger = get_logger(__name__)


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
    _is_export: bool = field(default=False, repr=False)
    _download_url: str | None = field(default=None, repr=False)
    # Reporters must include providerId when polling; stored here so _poll() can inject it.
    _provider_id: int | None = field(default=None, repr=False)

    def _poll(self) -> dict[str, object]:
        url = self.polling_url
        if self._provider_id is not None and "providerId" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}providerId={self._provider_id}"
        data: dict[str, object] = self._http.get(url).json()
        if download_url := data.get("downloadUrl"):
            self._download_url = str(download_url)
        return data

    def status(self) -> JobStatus:
        return JobStatus(self._poll()["status"])

    def wait(
        self,
        *,
        poll_interval: float = 5.0,
        timeout: float | None = None,
        on_status: Callable[[JobStatus], None] | None = None,
    ) -> "JobHandle":
        deadline = time.monotonic() + timeout if timeout is not None else None
        started = time.monotonic()
        previous: JobStatus | None = None
        while True:
            data = self._poll()
            current = JobStatus(data["status"])
            if current != previous:
                logger.info(
                    "job %d: %s (after %.0fs)", self.job_id, current.value,
                    time.monotonic() - started,
                )
                previous = current
            if on_status is not None:
                on_status(current)
            if current.is_terminal:
                if not current.is_successful:
                    logger.warning("job %d ended with %s", self.job_id, current.value)
                    raise JobFailedError(self.job_id, current.value)
                return self
            if deadline is not None and time.monotonic() >= deadline:
                logger.warning(
                    "job %d timed out after %.0fs (last status %s)",
                    self.job_id, time.monotonic() - started, current.value,
                )
                raise JobTimeoutError(self.job_id)
            time.sleep(poll_interval)

    def result(
        self,
        *,
        poll_interval: float = 5.0,
        timeout: float | None = None,
        on_status: Callable[[JobStatus], None] | None = None,
    ) -> bytes:
        if not self._is_export:
            raise TypeError(
                "result() is only valid on export handles (returned by etl_export, "
                "export_file, export_file_dl, export_dataset_file, or export_dataset_file_dl)"
            )
        self.wait(poll_interval=poll_interval, timeout=timeout, on_status=on_status)
        if self._download_url is None:
            raise RuntimeError("Export FINISHED but poll response contained no downloadUrl")
        return self._http.get(self._download_url).content

    def to_frames(
        self,
        *,
        poll_interval: float = 5.0,
        timeout: float | None = None,
        on_status: Callable[[JobStatus], None] | None = None,
    ) -> dict[str, Any]:
        """Wait for an export job and return its tables as DataFrames.

        Supports CSV (v4), Parquet (v5), and JSON (v3) export formats —
        see :func:`~reportnet._util.zip_to_frames`.

        Returns a dict keyed by table name (filename without extension).
        Requires polars or pandas (``pip install reportnet-client[dataframe]``).
        """
        from ._util import zip_to_frames

        return zip_to_frames(
            self.result(poll_interval=poll_interval, timeout=timeout, on_status=on_status)
        )
