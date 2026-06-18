from __future__ import annotations

from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Literal, Union

from ._http import HttpSession
from ._util import to_file_tuple
from .models import DataflowInfo, DatasetSchema, JobHandle, Reporter

if TYPE_CHECKING:
    from .dataflow import DataflowClient


class ReportnetClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.reportnet.europa.eu",
        timeout: float = 30.0,
    ) -> None:
        self._http = HttpSession(api_key=api_key, base_url=base_url, timeout=timeout)

    @classmethod
    def from_keyring(
        cls,
        dataflow_id: int | str,
        base_url: str = "https://api.reportnet.europa.eu",
        timeout: float = 30.0,
    ) -> "ReportnetClient":
        """Create a client using the API key stored in the system keychain."""
        from .keychain import get_key
        return cls(api_key=get_key(dataflow_id), base_url=base_url, timeout=timeout)

    def for_dataflow(
        self,
        dataflow_id: int,
        *,
        provider_id: int | None = None,
    ) -> "DataflowClient":
        """Return a DataflowClient that pre-fills dataflow_id (and optionally provider_id)."""
        from .dataflow import DataflowClient
        return DataflowClient(self, dataflow_id=dataflow_id, provider_id=provider_id)

    # ── Dataflow metadata ─────────────────────────────────────────────────────

    def get_dataflow(self, *, dataflow_id: int) -> DataflowInfo:
        """GET /dataflow/v1/{dataflowId} — name, type, status of a dataflow."""
        response = self._http.get(f"/dataflow/v1/{dataflow_id}")
        return DataflowInfo.from_dict(response.json())

    def get_reporters(self, *, dataflow_id: int) -> list[Reporter]:
        """GET /representative/v1/dataflow/{dataflowId} — countries/orgs reporting to a dataflow."""
        response = self._http.get(f"/representative/v1/dataflow/{dataflow_id}")
        return [Reporter.from_dict(r) for r in response.json()]

    def is_big_dataflow(self, *, dataflow_id: int) -> bool:
        """GET /dataflow/private/v1/{dataflowId}/isBigDataflow — BigData (DLT2) flag."""
        response = self._http.get(f"/dataflow/private/v1/{dataflow_id}/isBigDataflow")
        return bool(response.json())

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ReportnetClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ── Import ────────────────────────────────────────────────────────────────

    def import_file(
        self,
        *,
        dataset_id: int,
        dataflow_id: int,
        file: Union[str, Path, bytes, IO[bytes], object],
        filename: str | None = None,
        provider_id: int | None = None,
        table_schema_id: str | None = None,
        replace: bool = False,
        delimiter: str = "|",
        integration_id: int | None = None,
    ) -> JobHandle:
        """POST /dataset/v2/importFileData/{datasetId} — multipart upload."""
        name, content = to_file_tuple(file, filename)
        params: dict[str, object] = {
            "dataflowId": dataflow_id,
            "replace": str(replace).lower(),
            "delimiter": delimiter,
        }
        if provider_id is not None:
            params["providerId"] = provider_id
        if table_schema_id is not None:
            params["tableSchemaId"] = table_schema_id
        if integration_id is not None:
            params["integrationId"] = integration_id

        response = self._http.post(
            f"/dataset/v2/importFileData/{dataset_id}",
            params=params,
            files={"file": (name, content)},
        )
        return _make_job(response.json(), self._http, provider_id=provider_id)

    def etl_import(
        self,
        *,
        dataset_id: int,
        dataflow_id: int,
        tables: list[dict[str, object]],
        replace_data: bool = False,
    ) -> JobHandle:
        """POST /dataset/v1/{datasetId}/etlImport — JSON body, Citus datasets only."""
        response = self._http.post(
            f"/dataset/v1/{dataset_id}/etlImport",
            params={"dataflowId": dataflow_id, "replaceData": str(replace_data).lower()},
            json={"tables": tables},
        )
        return _make_job(response.json(), self._http)

    # ── Export ────────────────────────────────────────────────────────────────

    def etl_export(
        self,
        *,
        dataset_id: int,
        dataflow_id: int,
        provider_id: int | None = None,
        table_schema_id: str | None = None,
        include_attachments: bool = False,
        version: int = 4,
    ) -> JobHandle:
        """GET /dataset/v{version}/etlExport/{datasetId} — async, result is a ZIP of CSVs."""
        params: dict[str, object] = {
            "dataflowId": dataflow_id,
            "includeAttachments": str(include_attachments).lower(),
        }
        if provider_id is not None:
            params["providerId"] = provider_id
        if table_schema_id is not None:
            params["tableSchemaId"] = table_schema_id

        response = self._http.get(f"/dataset/v{version}/etlExport/{dataset_id}", params=params)
        return _make_job(response.json(), self._http, is_export=True, provider_id=provider_id)

    def export_file(
        self,
        *,
        dataset_id: int,
        table_schema_id: str,
        mime_type: Literal["csv", "xlsx"] = "csv",
        filters: dict[str, object] | None = None,
    ) -> JobHandle:
        """POST /dataset/exportFile — async single-table export."""
        response = self._http.post(
            "/dataset/exportFile",
            params={
                "datasetId": dataset_id,
                "tableSchemaId": table_schema_id,
                "mimeType": mime_type,
            },
            json=filters or {},
        )
        return _make_job(response.json(), self._http, is_export=True)

    def export_file_dl(
        self,
        *,
        dataset_id: int,
        table_schema_id: str,
        filters: dict[str, object] | None = None,
    ) -> JobHandle:
        """POST /dataset/exportFileDL — async single-table export, BigData variant."""
        response = self._http.post(
            "/dataset/exportFileDL",
            params={
                "datasetId": dataset_id,
                "tableSchemaId": table_schema_id,
                "mimeType": "csv",
            },
            json=filters or {},
        )
        return _make_job(response.json(), self._http, is_export=True)

    def export_dataset_file(
        self,
        *,
        dataset_id: int,
        mime_type: Literal["csv", "xlsx", "zip"] = "csv",
    ) -> JobHandle:
        """GET /dataset/exportDatasetFile — async whole-dataset export (all tables)."""
        response = self._http.get(
            "/dataset/exportDatasetFile",
            params={
                "datasetId": dataset_id,
                "mimeType": mime_type,
            },
        )
        return _make_job(response.json(), self._http, is_export=True)

    def export_dataset_file_dl(
        self,
        *,
        dataset_id: int,
    ) -> JobHandle:
        """GET /dataset/exportDatasetFileDL — async whole-dataset export, BigData variant."""
        response = self._http.get(
            "/dataset/exportDatasetFileDL",
            params={
                "datasetId": dataset_id,
                "mimeType": "zip",
            },
        )
        return _make_job(response.json(), self._http, is_export=True)

    # ── Validation ────────────────────────────────────────────────────────────

    def add_validation_job(
        self,
        *,
        dataset_id: int,
        dataflow_id: int,
        provider_id: int | None = None,
    ) -> JobHandle:
        """PUT /orchestrator/jobs/addValidationJob/{datasetId}."""
        params: dict[str, object] = {"dataflowId": dataflow_id}
        if provider_id is not None:
            params["providerId"] = provider_id
        response = self._http.put(
            f"/orchestrator/jobs/addValidationJob/{dataset_id}", params=params
        )
        data = response.json()
        # The API returns a bare integer job ID (not a dict with pollingUrl).
        if isinstance(data, int):
            return JobHandle(
                job_id=data,
                polling_url=_polling_url(data, dataset_id, dataflow_id, provider_id),
                _http=self._http,
                _provider_id=provider_id,
            )
        return _make_job(data, self._http, provider_id=provider_id)

    def list_group_validations(
        self,
        *,
        dataset_id: int,
        dataflow_id: int,
        provider_id: int | None = None,
    ) -> dict[str, object]:
        """GET /validation/listGroupValidations/{datasetId} — Citus datasets."""
        return self._get_validations(
            f"/validation/listGroupValidations/{dataset_id}", dataflow_id, provider_id
        )

    def list_group_validations_dl(
        self,
        *,
        dataset_id: int,
        dataflow_id: int,
        provider_id: int | None = None,
    ) -> dict[str, object]:
        """GET /validation/listGroupValidationsDL/{datasetId} — BigData datasets."""
        return self._get_validations(
            f"/validation/listGroupValidationsDL/{dataset_id}", dataflow_id, provider_id
        )

    def download_validation_snapshot(
        self,
        *,
        snapshot_id: int,
        dataset_id: int,
        dataflow_id: int,
        provider_id: int,
    ) -> bytes:
        """GET /downloadValidation/{snapshotId} — validation results for a release snapshot."""
        response = self._http.get(
            f"/downloadValidation/{snapshot_id}",
            params={
                "datasetId": dataset_id,
                "dataflowId": dataflow_id,
                "providerId": provider_id,
            },
        )
        return response.content

    def get_schema(self, *, dataset_id: int) -> DatasetSchema:
        """GET /dataschema/v1/datasetId/{datasetId} — table and field definitions."""
        response = self._http.get(f"/dataschema/v1/datasetId/{dataset_id}")
        return DatasetSchema.from_dict(response.json())

    def set_reference_dataset_updatable(
        self,
        *,
        dataset_id: int,
        dataflow_id: int,
        updatable: bool,
    ) -> None:
        """PUT /referenceDataset/{datasetId} — lock or unlock a reference dataset."""
        self._http.put(
            f"/referenceDataset/{dataset_id}",
            params={"dataflowId": dataflow_id, "updatable": str(updatable).lower()},
        )

    def delete_dataset_data(
        self,
        *,
        dataset_id: int,
        dataflow_id: int,
        provider_id: int | None = None,
        delete_prefilled_tables: bool = False,
    ) -> None:
        """DELETE /dataset/v1/{datasetId}/deleteDatasetData — remove all data from a dataset."""
        params: dict[str, object] = {
            "dataflowId": dataflow_id,
            "deletePrefilledTables": str(delete_prefilled_tables).lower(),
        }
        if provider_id is not None:
            params["providerId"] = provider_id
        self._http.delete(f"/dataset/v1/{dataset_id}/deleteDatasetData", params=params)

    def delete_table_data(
        self,
        *,
        dataset_id: int,
        table_schema_id: str,
        dataflow_id: int,
        provider_id: int | None = None,
    ) -> None:
        """DELETE /dataset/v1/{datasetId}/deleteTableData/{tableSchemaId}."""
        params: dict[str, object] = {"dataflowId": dataflow_id}
        if provider_id is not None:
            params["providerId"] = provider_id
        self._http.delete(
            f"/dataset/v1/{dataset_id}/deleteTableData/{table_schema_id}", params=params
        )

    def list_historic_releases(
        self,
        *,
        dataset_id: int,
        dataflow_id: int,
    ) -> list[dict[str, object]]:
        """GET /snapshot/v1/historicReleases — list releases submitted for a dataset."""
        response = self._http.get(
            "/snapshot/v1/historicReleases",
            params={"dataflowId": dataflow_id, "datasetId": dataset_id},
        )
        return response.json()  # type: ignore[no-any-return]

    def check_import_process(self, *, dataset_id: int) -> dict[str, object]:
        """GET /dataset/checkImportProcess/{datasetId} — lock/import status for a dataset."""
        response = self._http.get(f"/dataset/checkImportProcess/{dataset_id}")
        return response.json()  # type: ignore[no-any-return]

    def _get_validations(
        self, path: str, dataflow_id: int, provider_id: int | None
    ) -> dict[str, object]:
        params: dict[str, object] = {"dataflowId": dataflow_id}
        if provider_id is not None:
            params["providerId"] = provider_id
        response = self._http.get(path, params=params)
        return response.json()  # type: ignore[no-any-return]


def _make_job(
    data: dict[str, Any],
    http: HttpSession,
    *,
    provider_id: int | None = None,
    is_export: bool = False,
) -> JobHandle:
    job_id = data.get("jobId") or _extract_job_id(str(data["pollingUrl"]))
    return JobHandle(
        job_id=int(job_id),
        polling_url=str(data["pollingUrl"]),
        _http=http,
        _is_export=is_export,
        _provider_id=provider_id,
    )


def _polling_url(
    job_id: int, dataset_id: int, dataflow_id: int, provider_id: int | None = None
) -> str:
    url = (
        f"/orchestrator/jobs/pollForJobStatus/{job_id}"
        f"?datasetId={dataset_id}&dataflowId={dataflow_id}"
    )
    if provider_id is not None:
        url += f"&providerId={provider_id}"
    return url


def _extract_job_id(polling_url: str) -> int:
    # /orchestrator/jobs/pollForJobStatus/{jobId}?datasetId=...
    path = polling_url.split("?")[0]
    return int(path.rstrip("/").rsplit("/", 1)[-1])
