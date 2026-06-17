from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from ._http import HttpSession
from .exceptions import JobFailedError, JobTimeoutError


# ── Schema models ─────────────────────────────────────────────────────────────

class FieldType(str, Enum):
    TEXT = "TEXT"
    NUMBER_INTEGER = "NUMBER_INTEGER"
    NUMBER_DECIMAL = "NUMBER_DECIMAL"
    DATE = "DATE"
    DATETIME = "DATETIME"
    BOOLEAN = "BOOLEAN"
    CODELIST = "CODELIST"
    MULTISELECT_CODELIST = "MULTISELECT_CODELIST"
    LINK = "LINK"
    MULTISELECT_LINK = "MULTISELECT_LINK"
    ATTACHMENT = "ATTACHMENT"
    COORDINATE_LAT = "COORDINATE_LAT"
    COORDINATE_LONG = "COORDINATE_LONG"
    POINT = "POINT"
    LINESTRING = "LINESTRING"
    POLYGON = "POLYGON"

    @classmethod
    def _missing_(cls, value: object) -> "FieldType":
        # Pass unknown types through as opaque strings rather than raising.
        unknown = str.__new__(cls, str(value))
        unknown._value_ = str(value)
        unknown._name_ = str(value)
        return unknown


@dataclass(frozen=True)
class FieldSchema:
    id: str
    name: str
    type: FieldType
    description: str
    required: bool

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FieldSchema":
        return cls(
            id=d["id"],
            name=d["name"],
            type=FieldType(d.get("type", "TEXT")),
            description=d.get("description") or "",
            required=bool(d.get("required", False)),
        )


@dataclass(frozen=True)
class TableSchema:
    id: str
    name: str
    description: str
    fields: tuple[FieldSchema, ...]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TableSchema":
        raw_fields = d.get("recordSchema", {}).get("fieldSchema", [])
        return cls(
            id=d["idTableSchema"],
            name=d["nameTableSchema"],
            description=d.get("description") or "",
            fields=tuple(FieldSchema.from_dict(f) for f in raw_fields),
        )

    def required_columns(self) -> list[str]:
        """Names of fields that are required for import."""
        return [f.name for f in self.fields if f.required]

    def column_names(self) -> list[str]:
        """All field names in schema order."""
        return [f.name for f in self.fields]


@dataclass(frozen=True)
class DatasetSchema:
    id: str
    name: str
    description: str
    tables: tuple[TableSchema, ...]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DatasetSchema":
        return cls(
            id=d["idDataSetSchema"],
            name=d["nameDatasetSchema"],
            description=d.get("description") or "",
            tables=tuple(TableSchema.from_dict(t) for t in d.get("tableSchemas", [])),
        )

    def table(self, name: str) -> TableSchema:
        """Return the TableSchema with the given name, or raise KeyError."""
        for t in self.tables:
            if t.name == name:
                return t
        raise KeyError(f"No table named {name!r}; available: {[t.name for t in self.tables]}")


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
        while True:
            data = self._poll()
            current = JobStatus(data["status"])
            if on_status is not None:
                on_status(current)
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
        """Wait for an export job and return its CSVs as DataFrames.

        Returns a dict keyed by table name (filename without .csv extension).
        Requires polars or pandas (``pip install reportnet[dataframe]``).
        """
        from ._util import zip_to_frames

        return zip_to_frames(
            self.result(poll_interval=poll_interval, timeout=timeout, on_status=on_status)
        )
