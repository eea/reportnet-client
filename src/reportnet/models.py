"""Data models for Reportnet API responses.

These are plain frozen dataclasses that parse JSON payloads — they perform no
network I/O.  The asynchronous job machinery (:class:`~reportnet.JobHandle`,
:class:`~reportnet.JobStatus`) lives in :mod:`reportnet.jobs` because it holds
a live HTTP session; it is re-exported here for backwards compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeAlias

# Re-exported for backwards compatibility with `from reportnet.models import JobHandle`.
from .jobs import JobHandle, JobStatus

if TYPE_CHECKING:
    import pandas  # type: ignore[import-untyped]
    import polars

    NativeFrame: TypeAlias = polars.DataFrame | pandas.DataFrame

__all__ = [
    "ExportVerification",
    "ExportResult",
    "OperationEvidence",
    "ReadbackVerification",
    "SubmissionResult",
    "DataflowInfo",
    "DataflowContents",
    "Capabilities",
    "DataCollection",
    "EuDataset",
    "Reporter",
    "ReportingDataset",
    "ReferenceDataset",
    "TestDataset",
    "FieldType",
    "FieldSchema",
    "TableSchema",
    "DatasetSchema",
    "ValidationIssue",
    "ValidationResult",
    "JobHandle",
    "JobStatus",
]

# ── Dataflow models ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DataflowInfo:
    """Metadata returned by GET /dataflow/v1/{dataflowId}."""
    id: int
    name: str
    description: str
    type: str    # e.g. "REPORTING", "BUSINESS", "CITIZEN_SCIENCE"
    status: str  # e.g. "DESIGN", "DRAFT", "PUBLIC"
    big_data: bool = False  # BigData (DLT2) dataflow, from the "bigData" field

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DataflowInfo":
        return cls(
            id=int(d["id"]),
            name=d.get("name") or "",
            description=d.get("description") or "",
            type=d.get("type") or "",
            status=d.get("status") or "",
            big_data=bool(d.get("bigData", False)),
        )


@dataclass(frozen=True)
class Reporter:
    """A country/organisation registered to report within a dataflow.

    Returned by GET /representative/v1/dataflow/{dataflowId}.
    Use :meth:`DataflowClient.get_reporting_datasets` to find the actual
    dataset IDs for each reporter (one dataset per table schema).
    """
    id: int
    dataflow_id: int
    provider_id: int

    @classmethod
    def from_dict(cls, d: dict[str, Any], *, dataflow_id: int | None = None) -> "Reporter":
        return cls(
            id=int(d.get("id", 0)),
            # The API doesn't echo dataflowId in the representatives list response;
            # caller injects it from the URL parameter.
            dataflow_id=dataflow_id if dataflow_id is not None else int(d.get("dataflowId", 0)),
            provider_id=int(d.get("dataProviderId", 0)),
        )

    @property
    def country_code(self) -> str | None:
        """ISO 3166-1 alpha-2 country code, or None if provider_id is not in the mapping."""
        from .providers import by_id
        provider = by_id(self.provider_id)
        return provider.country_code if provider is not None else None

    @property
    def country_name(self) -> str | None:
        """Full country name, or None if provider_id is not in the mapping."""
        from .providers import by_id
        provider = by_id(self.provider_id)
        return provider.country_name if provider is not None else None


@dataclass(frozen=True)
class ReportingDataset:
    """One reporting dataset — a single table for a single reporter in a dataflow.

    Returned inside ``reportingDatasets`` by GET /dataflow/v1/{dataflowId}.
    Each reporter (country) has one ``ReportingDataset`` per table schema
    defined in the dataflow.
    """
    id: int
    name: str        # dataSetName — country/reporter name
    provider_id: int
    schema_id: str   # datasetSchema — the dataset schema ID
    table_name: str  # nameDatasetSchema — e.g. "Table1a", "Table7"
    status: str      # e.g. "PENDING", "FINAL"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReportingDataset":
        return cls(
            id=int(d["id"]),
            name=d.get("dataSetName") or "",
            provider_id=int(d["dataProviderId"]),
            schema_id=d.get("datasetSchema") or "",
            table_name=d.get("nameDatasetSchema") or "",
            status=d.get("status") or "",
        )

    @property
    def country_code(self) -> str | None:
        """ISO 3166-1 alpha-2 country code, or None if provider_id is not in the mapping."""
        from .providers import by_id
        provider = by_id(self.provider_id)
        return provider.country_code if provider is not None else None


@dataclass(frozen=True)
class ReferenceDataset:
    """A shared reference dataset (e.g. codelists) in a dataflow.

    Returned inside ``referenceDatasets`` by GET /dataflow/v1/{dataflowId}.
    Reference datasets are not tied to any specific reporter; they hold
    shared lookup data such as allowed codelist values.
    """
    id: int
    name: str              # dataSetName — e.g. "Reference Dataset - Codelist"
    schema_id: str         # datasetSchema
    updatable: bool        # whether the dataset can currently be edited
    public_filename: str | None  # publicFileName

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ReferenceDataset":
        return cls(
            id=int(d["id"]),
            name=d.get("dataSetName") or "",
            schema_id=d.get("datasetSchema") or "",
            updatable=bool(d.get("updatable", False)),
            public_filename=d.get("publicFileName") or None,
        )


@dataclass(frozen=True)
class TestDataset:
    """A test dataset — mirrors a reporting dataset schema for custodian testing.

    Returned inside ``testDatasets`` by GET /dataflow/v1/{dataflowId}.
    Test datasets share the same schema as their corresponding reporting
    datasets but are not submitted as part of the official reporting cycle.
    """
    __test__ = False  # suppress pytest collection warning

    id: int
    name: str       # dataSetName — e.g. "Test Dataset - Table1a"
    schema_id: str  # datasetSchema

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TestDataset":
        return cls(
            id=int(d["id"]),
            name=d.get("dataSetName") or "",
            schema_id=d.get("datasetSchema") or "",
        )


@dataclass(frozen=True)
class DataCollection:
    """An all-country dataset holding every reporter's *released* data.

    Returned inside ``dataCollections`` by GET /dataflow/v1/{dataflowId}.
    Where a ``ReportingDataset`` is one table for one reporter, a
    ``DataCollection`` is one table for *all* reporters — what a custodian
    wants when exporting a whole dataflow rather than country by country.

    Only released data appears here: a dataflow whose reporters are all
    ``PENDING`` has empty data collections.

    Note that the API does not populate ``nameDatasetSchema`` for these, so
    there is no separate table name — the table is part of ``name``
    (e.g. ``"Data Collection - Table1a"``). Match on ``schema_id`` rather than
    parsing that string when you need to pair one with a reporting dataset::

        contents = flow.get_dataflow_contents()
        by_schema = {dc.schema_id: dc for dc in contents.data_collections}
        collection = by_schema.get(reporting_dataset.schema_id)

    There is no name-based lookup helper for these yet, unlike
    :meth:`~reportnet.DataflowClient.reference_dataset`.
    """

    id: int
    name: str       # dataSetName — e.g. "Data Collection - Table1a"
    schema_id: str  # datasetSchema
    status: str | None
    due_date: str | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DataCollection":
        return cls(
            id=int(d["id"]),
            name=d.get("dataSetName") or "",
            schema_id=d.get("datasetSchema") or "",
            status=d.get("status") or None,
            due_date=d.get("dueDate") or None,
        )


@dataclass(frozen=True)
class EuDataset:
    """The EU-level aggregate of a data collection.

    Returned inside ``euDatasets`` by GET /dataflow/v1/{dataflowId}. One per
    table, populated from the corresponding :class:`DataCollection`.
    """

    id: int
    name: str       # dataSetName — e.g. "EU Dataset - Table1a"
    schema_id: str  # datasetSchema
    status: str | None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EuDataset":
        return cls(
            id=int(d["id"]),
            name=d.get("dataSetName") or "",
            schema_id=d.get("datasetSchema") or "",
            status=d.get("status") or None,
        )


@dataclass(frozen=True)
class DataflowContents:
    """Everything GET /dataflow/v1/{dataflowId} returns, parsed in one pass.

    ``get_dataflow``, ``get_reporting_datasets``, ``get_reference_datasets``,
    ``get_test_datasets`` and ``is_big_dataflow`` all read the *same* endpoint.
    Calling them individually costs one HTTP round-trip each; fetching a
    ``DataflowContents`` gets all of it for one.

    Example::

        contents = flow.get_dataflow_contents()
        print(contents.info.name, contents.info.big_data)
        for ds in contents.reporting_datasets:
            print(ds.country_code, ds.table_name, ds.id)
    """

    info: DataflowInfo
    reporting_datasets: tuple[ReportingDataset, ...]
    reference_datasets: tuple[ReferenceDataset, ...]
    test_datasets: tuple[TestDataset, ...]
    data_collections: tuple[DataCollection, ...] = ()
    eu_datasets: tuple[EuDataset, ...] = ()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DataflowContents":
        return cls(
            info=DataflowInfo.from_dict(d),
            reporting_datasets=tuple(
                ReportingDataset.from_dict(x) for x in d.get("reportingDatasets") or []
            ),
            reference_datasets=tuple(
                ReferenceDataset.from_dict(x) for x in d.get("referenceDatasets") or []
            ),
            test_datasets=tuple(TestDataset.from_dict(x) for x in d.get("testDatasets") or []),
            data_collections=tuple(
                DataCollection.from_dict(x) for x in d.get("dataCollections") or []
            ),
            eu_datasets=tuple(EuDataset.from_dict(x) for x in d.get("euDatasets") or []),
        )


@dataclass(frozen=True)
class Capabilities:
    """Inferred request scoping, not a complete permission matrix.

    Reportnet grants permissions per *key role*, and the API has no endpoint
    that reports the role — so this is probed. The distinction matters because
    it changes how requests must be built, not just what succeeds:
    a Reporter key **must** send ``providerId`` when importing, while a
    custodian key is refused if it does.

    Obtained from :meth:`~reportnet.DataflowClient.capabilities`; cached, since
    results may be refreshed after permissions change.

    Example::

        caps = flow.capabilities()
        if not caps.can_discover_datasets:
            print("dataset IDs must come from the Reportnet web UI")
    """

    dataflow_id: int
    can_read_dataflow: bool
    can_read_representatives: bool

    @property
    def role(self) -> str:
        """``"custodian"``, ``"reporter"``, or ``"none"``.

        Inferred, not reported: only custodian-level keys may read
        ``GET /dataflow/v1/{id}``. A key that can read neither probe is not
        usable on this dataflow at all.
        """
        if self.can_read_dataflow:
            return "custodian"
        if self.can_read_representatives:
            return "reporter"
        return "none"

    @property
    def is_usable(self) -> bool:
        """True if the key authenticates and can reach at least one endpoint."""
        return self.role != "none"

    @property
    def can_discover_datasets(self) -> bool:
        """True if dataset identifiers can be looked up by name.

        Both roles can. Custodian keys read the dataflow unscoped; reporter
        keys must send ``providerId`` and then see only their own reporting
        datasets, so they need a provider-scoped client
        (:meth:`~reportnet.DataflowClient.for_provider` or
        :meth:`~reportnet.DataflowClient.find_reporter`).
        """
        return self.is_usable

    @property
    def needs_provider_scope(self) -> bool:
        """True if reads must be scoped to a provider to be permitted.

        Reporter keys are refused an unscoped dataflow read.
        """
        return self.role == "reporter"

    @property
    def wants_provider_id(self) -> bool:
        """True if BigData writes must carry ``providerId``.

        Verified live on dataflow 2003: a Reporter key is refused without
        it, a custodian key is refused with it.
        """
        return self.role == "reporter"

    def summary(self) -> str:
        if not self.is_usable:
            return f"dataflow {self.dataflow_id}: key not usable"
        extra = "; reads must be provider-scoped" if self.needs_provider_scope else ""
        return f"dataflow {self.dataflow_id}: inferred {self.role} key{extra}"


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
    MULTIPOINT = "MULTIPOINT"
    MULTILINESTRING = "MULTILINESTRING"
    MULTIPOLYGON = "MULTIPOLYGON"

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
    # LINK / MULTISELECT_LINK fields reference a primary-key field in a reference dataset.
    referenced_schema_id: str | None = None  # idDataSetSchema of the reference dataset
    referenced_pk_id: str | None = None      # field schema ID of the PK column in that dataset

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FieldSchema":
        ref = d.get("referencedField") or {}
        return cls(
            id=d["id"],
            name=d["name"],
            type=FieldType(d.get("type", "TEXT")),
            description=d.get("description") or "",
            required=bool(d.get("required", False)),
            referenced_schema_id=ref.get("idDatasetSchema") or None,
            referenced_pk_id=ref.get("idPk") or None,
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

    def validate_frame(
        self,
        frame: object,
        *,
        codelists: dict[str, list[str]] | None = None,
    ) -> list[str]:
        """Check a DataFrame against this table schema before uploading.

        Returns a list of error strings; an empty list means the frame is
        safe to upload.  Checks:

        - All required columns are present.
        - CODELIST / LINK column values exist in *codelists* (when provided).

        Does **not** raise; callers decide how to handle errors.

        Args:
            frame: A polars or pandas DataFrame.
            codelists: Optional mapping returned by
                :meth:`DataflowClient.get_codelists`.

        Example::

            errors = schema.table("Table1a").validate_frame(df, codelists=codelists)
            if errors:
                raise ValueError("\\n".join(errors))
        """
        try:
            import narwhals as nw
        except ImportError:
            raise ImportError(
                "narwhals is required; install with: pip install reportnet-client[dataframe]"
            ) from None

        nwf = nw.from_native(frame, eager_only=True)  # type: ignore[call-overload]
        frame_cols = set(nwf.columns)
        errors: list[str] = []

        for f in self.fields:
            if f.required and f.name not in frame_cols:
                errors.append(f"Required column missing: {f.name!r} (type: {f.type.value})")

        if codelists:
            for f in self.fields:
                if f.name not in codelists or f.name not in frame_cols:
                    continue
                valid = set(codelists[f.name])
                bad = set(nwf[f.name].drop_nulls().unique().to_list()) - valid
                if bad:
                    shown = sorted(bad)[:5]
                    errors.append(
                        f"Column {f.name!r}: invalid values {shown!r} "
                        f"(valid: {sorted(codelists[f.name])[:5]!r}…)"
                    )

        return errors

    def cast_frame(
        self,
        frame: object,
        *,
        codelists: dict[str, list[str]] | None = None,
    ) -> NativeFrame:
        """Cast a DataFrame's columns to this table's schema types.

        Use this when reading data from Excel or CSV where columns arrive as
        the wrong type (e.g., integers as floats, dates as strings).  LINK /
        CODELIST columns are cast to ``Enum`` when *codelists* is provided,
        which rejects invalid values at cast time rather than silently uploading
        bad data.

        Raises :class:`ValueError` if required columns are missing or if any
        Enum cast fails.

        Args:
            frame: A polars or pandas DataFrame.
            codelists: Optional mapping returned by
                :meth:`DataflowClient.get_codelists`.

        Returns:
            The cast DataFrame in the same backend as the input.

        Example::

            import polars as pl

            raw = pl.read_excel("my_data.xlsx", sheet_name="Table1a")
            typed = schema.table("Table1a").cast_frame(raw, codelists=codelists)
            flow.import_file(dataset_id=..., file=typed)
        """
        from ._util import cast_frame as _cast_frame
        return _cast_frame(self, frame, codelists=codelists)

    def align_frame(self, frame: object) -> NativeFrame:
        """Return *frame* reshaped to exactly this table's columns, in schema order.

        Reportnet rejects any import whose header is not exactly the field list,
        so a frame missing a column the source never had is refused just like a
        typo. This adds absent fields as empty, drops columns the schema does
        not define, reorders the rest, and renders DATE fields as YYYY-MM-DD.

        :meth:`~reportnet.DataflowClient.import_frames` applies this for you;
        call it directly only when building a file to upload by another route.

        Example::

            frame = schema.table("Agglomerations").align_frame(raw)
        """
        from ._util import align_frame as _align_frame
        aligned, _added, _dropped = _align_frame(self, frame)
        return aligned

    def to_frame(self, *, codelists: dict[str, list[str]] | None = None) -> NativeFrame:
        """Return an empty DataFrame with columns and types matching this table.

        Useful for building import data with the correct schema, or for
        inspecting what the API expects before uploading.

        Args:
            codelists: Optional mapping of field name → valid values (from
                :meth:`DataflowClient.get_codelists`).  When provided, LINK
                columns use ``pl.Enum`` (polars) or ``CategoricalDtype`` (pandas)
                instead of plain strings.

        Requires ``pip install reportnet-client[dataframe]``.
        Returns a ``polars.DataFrame`` if polars is installed, else ``pandas.DataFrame``.

        Example::

            codelists = flow.get_codelists(dataset_id=93953, ref_dataset_id=12345)
            frame = schema.table("Table1a").to_frame(codelists=codelists)
            # LINK columns are now pl.Enum with the valid categories
        """
        from ._util import table_to_frame
        return table_to_frame(self, codelists=codelists)


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

    def to_frames(self, *, codelists: dict[str, list[str]] | None = None) -> dict[str, NativeFrame]:
        """Return a dict of empty DataFrames, one per table, keyed by table name.

        Args:
            codelists: Optional mapping of field name → valid values (from
                :meth:`DataflowClient.get_codelists`).  When provided, LINK
                columns use ``pl.Enum`` / ``CategoricalDtype`` instead of strings.

        Requires ``pip install reportnet-client[dataframe]``.

        Example::

            schema = client.get_schema(dataset_id=93953)
            frames = schema.to_frames()
            # {"Table1a": <empty DataFrame>, "Table1b": <empty DataFrame>}
            print(frames["Table1a"].dtypes)
        """
        from ._util import table_to_frame
        return {t.name: table_to_frame(t, codelists=codelists) for t in self.tables}


# ── Validation result models ──────────────────────────────────────────────────

@dataclass(frozen=True)
class ValidationIssue:
    """A single grouped validation result from listGroupValidationsDL."""
    level: str           # "BLOCKER", "ERROR", "WARNING", "INFO"
    message: str
    table: str | None
    field: str | None
    entity_type: str | None  # "TABLE", "FIELD", "RECORD", "DATASET"
    record_count: int
    short_code: str | None   # rule identifier, e.g. "RY_CHECK"


@dataclass(frozen=True)
class JobRecord:
    """One entry from ``GET /orchestrator/jobs`` — a job's status and timing.

    This is the only way to tell *which run* a validation listing describes.
    The listing endpoint returns no timestamp, run id or snapshot id, so a
    stale read is indistinguishable from a fresh one by content alone —
    identical numbers from changed data look exactly like a correct result.

    ``info`` is the same field :class:`~reportnet.JobFailedError` surfaces.
    """

    id: int
    job_type: str          # IMPORT | VALIDATION | EXPORT | RELEASE | …
    status: str            # QUEUED | IN_PROGRESS | FINISHED | CANCELED | …
    dataset_id: int | None
    added_at: datetime | None
    status_changed_at: datetime | None
    info: str | None

    @property
    def is_running(self) -> bool:
        """True while the job could still change the published results."""
        return self.status in ("QUEUED", "IN_PROGRESS")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobRecord":
        def when(value: object) -> datetime | None:
            if not isinstance(value, (int, float)) or not value:
                return None
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)

        return cls(
            id=int(d["id"]),
            job_type=str(d.get("jobType") or ""),
            status=str(d.get("jobStatus") or ""),
            dataset_id=int(d["datasetId"]) if d.get("datasetId") is not None else None,
            added_at=when(d.get("dateAdded")),
            status_changed_at=when(d.get("dateStatusChanged")),
            info=str(d["jobInfo"]) if d.get("jobInfo") else None,
        )


@dataclass
class ValidationResult:
    """Parsed result of a validation run returned by DataflowClient.validate().

    Attributes:
        dataset_id: The dataset that was validated.
        issues: Parsed list of :class:`ValidationIssue` objects (empty = no issues found).
        raw: The raw API response dict — inspect this if *issues* looks incomplete.

    Example::

        result = flow.validate(dataset_id=93953)
        if result.has_blockers:
            print("Blockers found — cannot submit")
            print(result.to_frame())
        elif result.has_errors:
            print("Errors found")
        else:
            print(result.summary())
    """

    dataset_id: int
    issues: list[ValidationIssue]
    raw: dict[str, Any]
    job: JobRecord | None = None
    superseded_by: JobRecord | None = None
    data_changed_at: "datetime | None" = None

    @property
    def is_stale(self) -> bool:
        """True when these results do not describe the data currently in the dataset.

        Reportnet publishes validation results with no timestamp or run id, and
        does not clear them while a new run is in flight — so a stale read looks
        exactly like a fresh one. Two ways to be stale, both seen on dataflow
        2003:

        - **A newer validation is running** (:attr:`superseded_by`). The listing
          keeps serving the previous run's totals; one such run reported the
          earlier numbers, unchanged, for over an hour.
        - **The data was imported after the last validation finished**
          (:attr:`data_changed_at` later than the run in :attr:`job`). The
          results describe data that is no longer there.

        When this is True, re-validate rather than acting on the numbers.
        """
        if self.superseded_by is not None:
            return True
        if self.job is None or self.data_changed_at is None:
            return False
        finished = self.job.status_changed_at
        return finished is not None and self.data_changed_at > finished

    @property
    def ok(self) -> bool:
        """True when there are no BLOCKER or ERROR level issues."""
        return not self.has_errors

    @property
    def has_blockers(self) -> bool:
        return any(i.level == "BLOCKER" for i in self.issues)

    @property
    def has_errors(self) -> bool:
        return any(i.level in ("BLOCKER", "ERROR") for i in self.issues)

    def summary(self) -> str:
        """Return a one-line summary of the validation result."""
        if not self.issues:
            return f"dataset {self.dataset_id}: no issues"
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.level] = counts.get(issue.level, 0) + 1
        parts = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        return f"dataset {self.dataset_id}: {sum(counts.values())} issue(s) — {parts}"

    def to_frame(self) -> "NativeFrame":
        """Return issues as a DataFrame: level, entity_type, table, field, record_count, message."""
        try:
            import narwhals as nw
        except ImportError:
            raise ImportError(
                "narwhals is required; install with: pip install reportnet-client[dataframe]"
            ) from None

        data: dict[str, list[Any]] = {
            "level":        [i.level for i in self.issues],
            "entity_type":  [i.entity_type or "" for i in self.issues],
            "table":        [i.table or "" for i in self.issues],
            "field":        [i.field or "" for i in self.issues],
            "record_count": [i.record_count for i in self.issues],
            "short_code":   [i.short_code or "" for i in self.issues],
            "message":      [i.message for i in self.issues],
        }

        try:
            import polars as pl
            return nw.from_dict(data, backend=pl).to_native()
        except ImportError:
            pass

        try:
            import pandas as pd
            return nw.from_dict(data, backend=pd).to_native()
        except ImportError:
            pass

        raise ImportError(
            "polars or pandas required; install with: pip install reportnet-client[dataframe]"
        )

    @classmethod
    def _from_raw(
        cls,
        dataset_id: int,
        raw: dict[str, Any],
        *,
        job: "JobRecord | None" = None,
        superseded_by: "JobRecord | None" = None,
        data_changed_at: "datetime | None" = None,
    ) -> "ValidationResult":
        """Parse listGroupValidationsDL response into structured issues.

        The API response looks like::

            {
              "idDataset": 93953,
              "errors": [
                {
                  "levelError": "BLOCKER",
                  "message": "...",
                  "nameTableSchema": "Table1a",
                  "nameFieldSchema": "",
                  "typeEntity": "TABLE",
                  "numberOfRecords": "3",
                  "shortCode": "RY_CHECK",
                  "idRule": null
                }
              ],
              "totalErrors": 1,
              ...
            }
        """
        issues: list[ValidationIssue] = []

        # API uses "errors" key; fall back to "validations" for forward-compat
        error_list = raw.get("errors") or raw.get("validations") or []
        if isinstance(error_list, list):
            for item in error_list:
                if not isinstance(item, dict):
                    continue
                # numberOfRecords arrives as a string in the live API
                raw_count = item.get("numberOfRecords") or 0
                issues.append(ValidationIssue(
                    level=str(item.get("levelError") or ""),
                    message=str(item.get("message") or ""),
                    table=item.get("nameTableSchema") or None,
                    field=item.get("nameFieldSchema") or None,
                    entity_type=item.get("typeEntity") or item.get("typeEntityEnum") or None,
                    record_count=int(raw_count),
                    short_code=item.get("shortCode") or None,
                ))

        return cls(dataset_id=dataset_id, issues=issues, raw=raw,
                   job=job, superseded_by=superseded_by, data_changed_at=data_changed_at)




@dataclass(frozen=True)
class ExportVerification:
    """Structural export checks. Empty tables are reported, not assumed incorrect.

    ``ok`` checks table/column coverage only, not values, row counts or QC rules.
    """

    dataset_id: int
    expected_tables: tuple[str, ...]
    actual_tables: tuple[str, ...]
    missing_tables: tuple[str, ...]
    unexpected_tables: tuple[str, ...]
    missing_columns: dict[str, tuple[str, ...]]
    unexpected_columns: dict[str, tuple[str, ...]]
    row_counts: dict[str, int]

    @property
    def empty_tables(self) -> tuple[str, ...]:
        return tuple(sorted(name for name, count in self.row_counts.items() if count == 0))

    @property
    def ok(self) -> bool:
        return not (self.missing_tables or self.unexpected_tables
                    or self.missing_columns or self.unexpected_columns)

    def summary(self) -> str:
        return (
            f"dataset {self.dataset_id}: structure {'matches' if self.ok else 'MISMATCH'}; "
            f"missing tables={list(self.missing_tables)}, "
            f"unexpected tables={list(self.unexpected_tables)}, "
            f"missing columns={self.missing_columns}, "
            f"unexpected columns={self.unexpected_columns}; "
            f"empty tables={list(self.empty_tables)}"
        )


@dataclass(frozen=True)
class ExportResult:
    """Downloaded frames and their structural verification; no rows are discarded."""

    frames: dict[str, Any]
    verification: ExportVerification


@dataclass(frozen=True)
class OperationEvidence:
    """Latest observation for one exact request scope on this client/key.

    None means not checked, never permission granted. HTTP acceptance,
    structural payload checks and workflow readback are separate facts.
    ``detail`` contains diagnostic stages, not credentials or data rows.
    """

    operation: str
    dataflow_id: int
    dataset_id: int | None
    provider_id: int | None
    version: int | None
    table_schema_id: str | None
    observed_at: str
    request_accepted: bool | None
    payload_verified: bool | None = None
    workflow_verified: bool | None = None
    detail: str = ""
    data_provider_codes: str | None = None


@dataclass(frozen=True)
class ReadbackVerification:
    """Comparison of full row multisets; duplicate multiplicity is preserved."""

    dataset_id: int
    missing_rows: dict[str, int]
    unexpected_rows: dict[str, int]

    @property
    def ok(self) -> bool:
        return not (self.missing_rows or self.unexpected_rows)

    def summary(self) -> str:
        return (f"dataset {self.dataset_id}: readback {'matches' if self.ok else 'MISMATCH'}; "
                f"missing rows={self.missing_rows}, unexpected rows={self.unexpected_rows}")


@dataclass(frozen=True)
class SubmissionResult:
    """Preparation outcome, never an API release or a guarantee of acceptance."""

    dataset_id: int
    import_job_ids: tuple[int, ...]
    export: ExportResult
    readback: ReadbackVerification
    validation: ValidationResult

    @property
    def ready_for_review(self) -> bool:
        return self.export.verification.ok and self.readback.ok and self.validation.ok
