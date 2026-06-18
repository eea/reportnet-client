from __future__ import annotations

from pathlib import Path
from typing import IO, TYPE_CHECKING, Literal, Union

from .models import DataflowInfo, DatasetSchema, JobHandle, Reporter

if TYPE_CHECKING:
    from .client import ReportnetClient


class DataflowClient:
    """Convenience wrapper around ReportnetClient scoped to a single dataflow.

    Obtain via ``client.for_dataflow(dataflow_id, provider_id=...)``.

    The Reportnet hierarchy is::

        Dataflow
          └── Reporter / DataProvider (country or organisation)
                └── Dataset (reporting dataset, one per reporter)
          └── Reference Datasets (shared; no provider_id)

    Usage::

        # Custodian / no specific reporter
        df = client.for_dataflow(1619)
        df.get_dataflow()          # dataflow metadata
        df.get_reporters()         # list of countries and their dataset IDs

        # Scoped to a specific reporter country
        ie = df.for_provider(42)
        ie.import_file(dataset_id=93953, file="data.csv")
        ie.add_validation_job(dataset_id=93953)
        frames = ie.etl_export(dataset_id=93953).to_frames()

        # Reference datasets (custodian only, no provider_id)
        df.import_file(dataset_id=REF_DS_ID, file="codelists.csv")
        df.set_reference_dataset_updatable(dataset_id=REF_DS_ID, updatable=False)
    """

    def __init__(
        self,
        client: "ReportnetClient",
        dataflow_id: int,
        *,
        provider_id: int | None = None,
    ) -> None:
        self._client = client
        self._dataflow_id = dataflow_id
        self._provider_id = provider_id

    def _pid(self, override: int | None) -> int | None:
        """Return override if given, else fall back to the stored provider_id."""
        return override if override is not None else self._provider_id

    def for_provider(self, provider_id: int) -> "DataflowClient":
        """Return a new DataflowClient scoped to a specific reporter / country.

        Example::

            df = client.for_dataflow(1619)
            ie = df.for_provider(42)   # Ireland's provider ID
            ie.import_file(dataset_id=93953, file="ireland.csv")
        """
        return DataflowClient(self._client, self._dataflow_id, provider_id=provider_id)

    # ── Dataflow metadata ─────────────────────────────────────────────────────

    def get_dataflow(self) -> DataflowInfo:
        """Return name, type and status of this dataflow."""
        return self._client.get_dataflow(dataflow_id=self._dataflow_id)

    def get_reporters(self) -> list[Reporter]:
        """Return the list of countries/organisations and their dataset IDs."""
        return self._client.get_reporters(dataflow_id=self._dataflow_id)

    def is_big_dataflow(self) -> bool:
        """Return True if this is a BigData (DLT2) dataflow."""
        return self._client.is_big_dataflow(dataflow_id=self._dataflow_id)

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

    # ── Schema ────────────────────────────────────────────────────────────────

    def get_schema(self, *, dataset_id: int) -> DatasetSchema:
        return self._client.get_schema(dataset_id=dataset_id)

    # ── Dataset management ────────────────────────────────────────────────────

    def delete_dataset_data(
        self,
        *,
        dataset_id: int,
        provider_id: int | None = None,
        delete_prefilled_tables: bool = False,
    ) -> None:
        """Remove all data from a dataset (use before a full replace import)."""
        self._client.delete_dataset_data(
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
            provider_id=self._pid(provider_id),
            delete_prefilled_tables=delete_prefilled_tables,
        )

    def delete_table_data(
        self,
        *,
        dataset_id: int,
        table_schema_id: str,
        provider_id: int | None = None,
    ) -> None:
        """Remove all data from a single table within a dataset."""
        self._client.delete_table_data(
            dataset_id=dataset_id,
            table_schema_id=table_schema_id,
            dataflow_id=self._dataflow_id,
            provider_id=self._pid(provider_id),
        )

    def list_historic_releases(self, *, dataset_id: int) -> list[dict[str, object]]:
        """Return all releases (submissions) made for a dataset."""
        return self._client.list_historic_releases(
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
        )

    def check_import_process(self, *, dataset_id: int) -> dict[str, object]:
        """Return lock/import status for a dataset."""
        return self._client.check_import_process(dataset_id=dataset_id)

    def set_reference_dataset_updatable(
        self,
        *,
        dataset_id: int,
        updatable: bool,
    ) -> None:
        """Lock (updatable=False) or unlock (updatable=True) a reference dataset."""
        self._client.set_reference_dataset_updatable(
            dataset_id=dataset_id,
            dataflow_id=self._dataflow_id,
            updatable=updatable,
        )
