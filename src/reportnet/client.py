"""The low-level client — one method per Reportnet API operation.

Layering rule (see also :mod:`reportnet.dataflow`):

* ``ReportnetClient`` owns every quirk that is a property of the *endpoint* —
  URL shape, parameter names, response oddities, and API version selection.
  Calling any method here directly is always correct.
* ``DataflowClient`` owns only *scoping* — deciding which IDs get filled in
  when the caller omits them.

Endpoint knowledge therefore lives in exactly one place, and the two layers
can never disagree about how to talk to the API.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Literal, Union

from ._http import HttpSession
from ._log import get_logger
from ._util import to_file_tuple
from .jobs import JobHandle
from .models import (
    Capabilities,
    DataflowContents,
    DataflowInfo,
    DatasetSchema,
    ReferenceDataset,
    Reporter,
    ReportingDataset,
    TestDataset,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from .dataflow import DataflowClient


PRODUCTION_URL = "https://api.reportnet.europa.eu"
SANDBOX_URL = "https://sandbox.reportnet.europa.eu"


class ReportnetClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = PRODUCTION_URL,
        timeout: float = 60.0,
    ) -> None:
        """Args:
            timeout: HTTP request timeout in seconds. The default is generous
                because GET /dataflow/v1/{id} is slow on large dataflows —
                30s was low enough to ReadTimeout on one measured live, and a
                timeout there also breaks every method that reads it. Raise it
                further for very large dataflows.
        """
        self._http = HttpSession(api_key=api_key, base_url=base_url, timeout=timeout)
        # bigData-ness is immutable for a given dataflow, so this is safe to keep
        # for the lifetime of the client. Shared with DataflowClient, which
        # delegates rather than keeping a second copy.
        self._big_data_cache: dict[int, bool] = {}
        # A key's role never changes, so this is safe for the client's lifetime.
        self._capabilities_cache: dict[int, Capabilities] = {}

    @classmethod
    def from_keyring(
        cls,
        dataflow_id: int | str,
        base_url: str | None = None,
        *,
        sandbox: bool = False,
        timeout: float = 60.0,
    ) -> "ReportnetClient":
        """Create a client using the API key stored in the system keychain.

        Args:
            dataflow_id: The dataflow ID the key was stored under.
            base_url: API base URL.  Defaults to :data:`SANDBOX_URL` when
                ``sandbox=True``, otherwise :data:`PRODUCTION_URL`.
            sandbox: If ``True``, use the sandbox environment and look up the
                sandbox key (stored separately from the production key).
            timeout: HTTP request timeout in seconds.

        Examples::

            # Production (default)
            client = ReportnetClient.from_keyring(1619)

            # Sandbox
            client = ReportnetClient.from_keyring(1619, sandbox=True)
        """
        from .keychain import get_key
        if base_url is None:
            base_url = SANDBOX_URL if sandbox else PRODUCTION_URL
        return cls(
            api_key=get_key(dataflow_id, sandbox=sandbox),
            base_url=base_url,
            timeout=timeout,
        )

    def for_dataflow(
        self,
        dataflow_id: int,
        *,
        provider_id: int | None = None,
    ) -> "DataflowClient":
        """Return a DataflowClient that pre-fills dataflow_id (and optionally provider_id)."""
        from .dataflow import DataflowClient
        return DataflowClient(self, dataflow_id=dataflow_id, provider_id=provider_id)

    def ping(self, *, dataflow_id: int) -> bool:
        """Return True if the API key is usable for *dataflow_id*.

        Raises on network errors, so transient connectivity issues surface as
        exceptions rather than a silent False.

        A 403 is **not** treated as a bad key. Reporter-scoped keys (a Lead
        Reporter, say) are forbidden from ``GET /dataflow/v1/{id}`` while being
        perfectly valid for the endpoints they do own — verified live on
        dataflow 2003, where a Lead Reporter key 403s here yet imports
        successfully. Reporting such a key as revoked sends users chasing a
        credential problem that doesn't exist, so this falls back to the
        representatives endpoint before giving up.

        Only a 401, or a 403 from *both* probes, returns False.

        Example::

            if not client.ping(dataflow_id=1619):
                raise RuntimeError("API key is invalid or has been revoked")
        """
        from .exceptions import AuthError
        try:
            self._http.get(f"/dataflow/v1/{dataflow_id}")
            return True
        except AuthError as exc:
            # Only a genuine 403 means "authenticated but not permitted here".
            # A 401 — or a gateway-wrapped auth failure, which arrives as 500 —
            # means the key itself is bad, and no other endpoint will accept it.
            if exc.status_code != 403:
                return False
            logger.debug(
                "ping: /dataflow/v1/%s returned 403; retrying via the representatives "
                "endpoint, which reporter-scoped keys can read",
                dataflow_id,
            )
        try:
            self._http.get(f"/representative/v1/dataflow/{dataflow_id}")
            logger.info(
                "API key for dataflow %s is valid but not authorised for "
                "GET /dataflow/v1/%s — typical of a reporter-scoped key",
                dataflow_id, dataflow_id,
            )
            return True
        except AuthError:
            return False

    def capabilities(self, *, dataflow_id: int) -> Capabilities:
        """Probe what this API key is allowed to do on *dataflow_id*.

        Reportnet has no endpoint reporting a key's role, and the role changes
        how requests must be *built* — a Lead Reporter key must send
        ``providerId`` on BigData writes, a custodian key is refused if it
        does. So the library probes: at most two cheap GETs, cached per client.

        Example::

            caps = client.capabilities(dataflow_id=2003)
            print(caps.summary())      # "dataflow 2003: reporter key; cannot discover dataset IDs"
        """
        cached = self._capabilities_cache.get(dataflow_id)
        if cached is not None:
            return cached

        from .exceptions import AuthError

        can_read_dataflow = False
        can_read_representatives = False
        try:
            self.get_dataflow_contents(dataflow_id=dataflow_id)
            can_read_dataflow = True
            can_read_representatives = True  # custodian keys can read both
        except AuthError:
            try:
                self._http.get(f"/representative/v1/dataflow/{dataflow_id}")
                can_read_representatives = True
            except AuthError:
                pass

        caps = Capabilities(
            dataflow_id=dataflow_id,
            can_read_dataflow=can_read_dataflow,
            can_read_representatives=can_read_representatives,
        )
        logger.info("capabilities: %s", caps.summary())
        self._capabilities_cache[dataflow_id] = caps
        return caps

    # ── Dataflow metadata ─────────────────────────────────────────────────────

    def get_dataflow_contents(self, *, dataflow_id: int) -> DataflowContents:
        """GET /dataflow/v1/{dataflowId} — the whole payload, parsed in one pass.

        ``get_dataflow``, ``get_reporting_datasets``, ``get_reference_datasets``
        and ``get_test_datasets`` each read this same endpoint, so calling them
        individually costs one HTTP round-trip each. Use this when you need more
        than one of them.

        Example::

            contents = client.get_dataflow_contents(dataflow_id=1619)
            contents.info.name
            contents.reporting_datasets
        """
        contents = DataflowContents.from_dict(self._http.get(f"/dataflow/v1/{dataflow_id}").json())
        self._big_data_cache[dataflow_id] = contents.info.big_data
        return contents

    def get_dataflow(self, *, dataflow_id: int) -> DataflowInfo:
        """GET /dataflow/v1/{dataflowId} — name, type, status of a dataflow."""
        return self.get_dataflow_contents(dataflow_id=dataflow_id).info

    def get_reporters(self, *, dataflow_id: int) -> list[Reporter]:
        """GET /representative/v1/dataflow/{dataflowId} — countries/orgs reporting to a dataflow."""
        response = self._http.get(f"/representative/v1/dataflow/{dataflow_id}")
        return [Reporter.from_dict(r, dataflow_id=dataflow_id) for r in response.json()]

    def get_reporting_datasets(self, *, dataflow_id: int) -> list[ReportingDataset]:
        """GET /dataflow/v1/{dataflowId} — all reporting datasets (one per provider × table).

        Each country (reporter) has one dataset per table schema defined in the dataflow.
        Filter by ``provider_id`` to get all datasets for a specific country.
        """
        return list(self.get_dataflow_contents(dataflow_id=dataflow_id).reporting_datasets)

    def get_reference_datasets(self, *, dataflow_id: int) -> list[ReferenceDataset]:
        """GET /dataflow/v1/{dataflowId} — all reference datasets for a dataflow.

        Reference datasets hold shared lookup data such as codelists.
        They are not tied to any specific reporter.
        """
        return list(self.get_dataflow_contents(dataflow_id=dataflow_id).reference_datasets)

    def get_test_datasets(self, *, dataflow_id: int) -> list[TestDataset]:
        """GET /dataflow/v1/{dataflowId} — all test datasets for a dataflow.

        Test datasets mirror the reporting schema and are used by custodians
        to verify validation rules before the reporting period opens.
        """
        return list(self.get_dataflow_contents(dataflow_id=dataflow_id).test_datasets)

    def is_big_dataflow(self, *, dataflow_id: int) -> bool:
        """Return True if *dataflow_id* is a BigData (DLT2) dataflow.

        Reads the ``bigData`` field from GET /dataflow/v1/{dataflowId}. The
        dedicated GET /dataflow/private/v1/{dataflowId}/isBigDataflow endpoint
        looks purpose-built for this but 404s for API-key auth regardless of
        the dataflow's actual BigData status, so it isn't used here.

        Cached per client — a dataflow never changes backend.
        """
        cached = self._big_data_cache.get(dataflow_id)
        if cached is None:
            cached = self.get_dataflow_contents(dataflow_id=dataflow_id).info.big_data
        return cached

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
        name, content = to_file_tuple(file, filename, delimiter=delimiter)
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
            files={"file": (name, content, "text/csv")},
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
        """POST /dataset/v1/{datasetId}/etlImport — JSON body, Citus datasets only.

        Every record must carry a ``countryCode``. Omitting it does *not* fail:
        the job is accepted and reports ``FINISHED`` having imported nothing,
        so a warning is raised here rather than letting the silence stand.
        """
        _warn_on_records_without_country_code(tables)
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
        data_provider_codes: str | None = None,
        table_schema_id: str | None = None,
        include_attachments: bool = False,
        version: int | None = None,
    ) -> JobHandle:
        """GET /dataset/v{version}/etlExport/{datasetId} — async export.

        v4 (BigData/DLT2): result is a ZIP of CSVs.
        v5 (analytics, opt-in): result is a ZIP of Parquet files — same shape
        as v4, smaller and faster to load; never selected automatically, pass
        ``version=5`` explicitly.
        v3 (Citus): result is JSON; requires ``data_provider_codes`` (ISO country code).

        When *version* is ``None`` (the default), v3 vs v4 is chosen for you
        from the dataflow's backend via :meth:`is_big_dataflow` — sending the
        wrong version mostly "succeeds" but returns a differently-shaped
        payload, so guessing is worse than one extra lookup. The result is
        cached per client; pass *version* explicitly to skip the lookup.
        """
        if version is None:
            version = 4 if self.is_big_dataflow(dataflow_id=dataflow_id) else 3
        params: dict[str, object] = {
            "dataflowId": dataflow_id,
            "includeAttachments": str(include_attachments).lower(),
        }
        if provider_id is not None:
            params["providerId"] = provider_id
        if data_provider_codes is not None:
            params["dataProviderCodes"] = data_provider_codes
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


def _warn_on_records_without_country_code(tables: list[dict[str, Any]]) -> None:
    """Warn if any etlImport record omits ``countryCode``.

    The API drops such records and still reports the job FINISHED, so this is
    the only signal the caller gets that nothing was written.
    """
    offenders: list[str] = []
    for table in tables:
        records = table.get("records") or []
        if not isinstance(records, list):
            continue
        missing = sum(
            1
            for r in records
            if isinstance(r, dict) and not r.get("countryCode")
        )
        if missing:
            name = str(table.get("tableName", "<unnamed>"))
            offenders.append(f"{name} ({missing}/{len(records)} records)")

    if not offenders:
        return
    message = (
        "etlImport records without countryCode: "
        + ", ".join(offenders)
        + ". The API silently discards these and still reports the job as "
        "FINISHED — set countryCode on every record."
    )
    logger.warning(message)
    warnings.warn(message, stacklevel=3)


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
