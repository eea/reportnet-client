"""Reporter orchestration using public client operations; no endpoint knowledge."""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from ._log import get_logger
from ._util import to_file_tuple
from .exceptions import CodelistResolutionError, ReadbackVerificationError, ReportnetError
from .models import FieldType, ReadbackVerification, SubmissionResult
from .verification import frame_rows, row_counts

if TYPE_CHECKING:
    from .dataflow import DataflowClient

logger = get_logger(__name__)


def prepare_submission(
    flow: DataflowClient, *, dataset_id: int, frames: dict[str, object],
    replace: bool, codelists: dict[str, list[str]] | None, strict_codelists: bool,
    poll_interval: float, timeout: float,
) -> SubmissionResult:
    if flow._provider_id is None:
        raise ValueError("Scope the reporter workflow with for_provider() or find_reporter()")
    if not frames:
        raise ValueError("Provide at least one non-empty table to upload")
    if timeout <= 0 or poll_interval < 0:
        raise ValueError("timeout must be positive and poll_interval non-negative")
    # Establish membership before writing to an explicitly supplied dataset ID.
    own = flow.get_reporting_datasets()
    if not any(ds.id == dataset_id for ds in own):
        raise ValueError(f"Dataset {dataset_id} is not a reporting dataset in this provider scope")
    schema = flow.get_schema(dataset_id=dataset_id)
    tables = {t.name: t for t in schema.tables}
    unknown = set(frames) - set(tables)
    if unknown:
        raise ValueError(f"Unknown upload tables: {sorted(unknown)}")

    unresolved = sorted({f.name for name in frames for f in tables[name].fields
                         if f.type in {FieldType.LINK, FieldType.CODELIST,
                                       FieldType.MULTISELECT_LINK, FieldType.MULTISELECT_CODELIST}
                         and (not codelists or not codelists.get(f.name))})
    if unresolved:
        message = f"Local code-list checks unavailable for {unresolved}; RN3 validation is required"
        logger.warning(message)
        if strict_codelists:
            raise CodelistResolutionError(unresolved, message)
        # workflows -> DataflowClient.prepare_submission -> caller
        warnings.warn(message, UserWarning, stacklevel=3)

    prepared = {}
    uploads = {}
    # Preflight every table before the first import, including serialization.
    for name, frame in frames.items():
        table = tables[name]
        errors = table.validate_frame(frame, codelists=codelists)
        rows = frame_rows(frame)
        if not rows:
            errors.append("Empty uploads are not supported; use explicit dataset management")
        columns = set(rows[0]) if rows else set()
        if columns - set(table.column_names()):
            errors.append(f"Unknown columns: {sorted(columns - set(table.column_names()))}")
        if any(row.get(f.name) in (None, "") for row in rows for f in table.fields if f.required):
            errors.append("Required fields contain missing values")
        if errors:
            raise ValueError(f"{name}: {'; '.join(errors)}")
        prepared[name] = row_counts(frame, table)
        uploads[name] = to_file_tuple(frame, filename=f"{name}.csv", delimiter="|")

    baseline = flow.export_frames(
        dataset_id=dataset_id, poll_interval=poll_interval, timeout=timeout
    )
    expected = {name: row_counts(baseline.frames[name], table) for name, table in tables.items()}
    for name, rows_to_add in prepared.items():
        expected[name] = rows_to_add if replace else expected[name] + rows_to_add

    jobs = []
    for name, (filename, payload) in uploads.items():
        logger.info("uploading %s to dataset %d", name, dataset_id)
        job = flow.import_file(dataset_id=dataset_id, file=payload, filename=filename,
                               table_schema_id=tables[name].id, replace=replace, delimiter="|")
        jobs.append(job.job_id)
        job.wait(poll_interval=poll_interval, timeout=timeout)

    exported = flow.export_frames(
        dataset_id=dataset_id, poll_interval=poll_interval, timeout=timeout
    )
    missing = {}
    unexpected = {}
    for name, table in tables.items():
        actual = row_counts(exported.frames[name], table)
        n_missing = sum((expected[name] - actual).values())
        n_unexpected = sum((actual - expected[name]).values())
        if n_missing:
            missing[name] = n_missing
        if n_unexpected:
            unexpected[name] = n_unexpected
    readback = ReadbackVerification(dataset_id, missing, unexpected)
    flow._client._record_evidence(
        "submission_readback", dataflow_id=flow._dataflow_id, dataset_id=dataset_id,
        provider_id=flow._provider_id, request_accepted=True,
        payload_verified=True, workflow_verified=readback.ok, detail=readback.summary(),
    )
    if not readback.ok:
        logger.warning(readback.summary())
        raise ReadbackVerificationError(readback)

    validation = flow.validate(dataset_id=dataset_id, poll_interval=poll_interval, timeout=timeout)
    # An unrecognised response must not look like a clean validation run.
    raw_errors = validation.raw.get("errors")
    if (not isinstance(raw_errors, list)
            or len(validation.issues) != len(raw_errors)
            or any(i.level not in {"BLOCKER", "ERROR", "WARNING", "INFO"}
                   for i in validation.issues)
            or (not validation.issues and int(validation.raw.get("totalErrors") or 0) > 0)):
        raise ReportnetError("Validation response cannot establish a reliable result; inspect RN3")
    if validation.raw.get("idDataset", dataset_id) != dataset_id:
        raise ReportnetError("Validation response identifies a different dataset")
    return SubmissionResult(dataset_id, tuple(jobs), exported, readback, validation)
