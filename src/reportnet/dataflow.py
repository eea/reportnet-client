from __future__ import annotations

from pathlib import Path
from typing import IO, TYPE_CHECKING, Literal, Union

from .models import JobHandle

if TYPE_CHECKING:
    from .client import ReportnetClient


class DataflowClient:
    """Convenience wrapper around ReportnetClient that pre-fills dataflow_id.

    Obtain one via ``client.for_dataflow(dataflow_id, provider_id=...)``.
    The underlying ReportnetClient manages the HTTP session lifecycle.
    """

    def __init__(
        self,
        client: "ReportnetClient",  # noqa: F821 — resolved at runtime
        dataflow_id: int,
        *,
        provider_id: int | None = None,
    ) -> None:
        self._client = client
        self._dataflow_id = dataflow_id
        self._provider_id = provider_id

    def _pid(self, override: int | None) -> int | None:
        """Return override if given, otherwise fall back to the stored default."""
        return override if override is not None else self._provider_id

    # ── Import ────────────────────────────────────────────────────────────────

    def import_file(
        self,
        *,
        dataset_id: int,
        file: Union[str, Path, bytes, IO[bytes], object],
        filename: str | None = None,
        provider_id: int | None = None,
        table_schema_id: str | None = None,
        replace: bool = False,
        delimiter: str = "|",
        integration_id: int | None = None,
    ) -> JobHandle:
        return self._client.import_file(
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
            file=file,
            filename=filename,
            provider_id=self._pid(provider_id),
            table_schema_id=table_schema_id,
            replace=replace,
            delimiter=delimiter,
            integration_id=integration_id,
        )

    def etl_import(
        self,
        *,
        dataset_id: int,
        tables: list[dict[str, object]],
        replace_data: bool = False,
    ) -> JobHandle:
        return self._client.etl_import(
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
            tables=tables,
            replace_data=replace_data,
        )

    # ── Export ────────────────────────────────────────────────────────────────

    def etl_export(
        self,
        *,
        dataset_id: int,
        provider_id: int | None = None,
        table_schema_id: str | None = None,
        include_attachments: bool = False,
        version: int = 4,
    ) -> JobHandle:
        return self._client.etl_export(
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
            provider_id=self._pid(provider_id),
            table_schema_id=table_schema_id,
            include_attachments=include_attachments,
            version=version,
        )

    def export_file(
        self,
        *,
        dataset_id: int,
        table_schema_id: str,
        mime_type: Literal["csv", "xlsx"] = "csv",
        filters: dict[str, object] | None = None,
    ) -> JobHandle:
        return self._client.export_file(
            dataset_id=dataset_id,
            table_schema_id=table_schema_id,
            mime_type=mime_type,
            filters=filters,
        )

    def export_file_dl(
        self,
        *,
        dataset_id: int,
        table_schema_id: str,
        filters: dict[str, object] | None = None,
    ) -> JobHandle:
        return self._client.export_file_dl(
            dataset_id=dataset_id,
            table_schema_id=table_schema_id,
            filters=filters,
        )

    def export_dataset_file(
        self,
        *,
        dataset_id: int,
        mime_type: Literal["csv", "xlsx", "zip"] = "csv",
    ) -> JobHandle:
        return self._client.export_dataset_file(
            dataset_id=dataset_id,
            mime_type=mime_type,
        )

    def export_dataset_file_dl(
        self,
        *,
        dataset_id: int,
    ) -> JobHandle:
        return self._client.export_dataset_file_dl(dataset_id=dataset_id)

    # ── Validation ────────────────────────────────────────────────────────────

    def add_validation_job(
        self,
        *,
        dataset_id: int,
        provider_id: int | None = None,
    ) -> JobHandle:
        return self._client.add_validation_job(
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
            provider_id=self._pid(provider_id),
        )

    def list_group_validations(
        self,
        *,
        dataset_id: int,
        provider_id: int | None = None,
    ) -> dict[str, object]:
        return self._client.list_group_validations(
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
            provider_id=self._pid(provider_id),
        )

    def list_group_validations_dl(
        self,
        *,
        dataset_id: int,
        provider_id: int | None = None,
    ) -> dict[str, object]:
        return self._client.list_group_validations_dl(
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
            provider_id=self._pid(provider_id),
        )

    def download_validation_snapshot(
        self,
        *,
        snapshot_id: int,
        dataset_id: int,
        provider_id: int | None = None,
    ) -> bytes:
        pid = self._pid(provider_id)
        if pid is None:
            raise ValueError(
                "provider_id is required for download_validation_snapshot; "
                "pass it here or set it on DataflowClient."
            )
        return self._client.download_validation_snapshot(
            snapshot_id=snapshot_id,
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
            provider_id=pid,
        )

    def set_reference_dataset_updatable(
        self,
        *,
        dataset_id: int,
        updatable: bool,
    ) -> None:
        self._client.set_reference_dataset_updatable(
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
            updatable=updatable,
        )
