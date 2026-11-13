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
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Callable, Literal, Mapping, Sequence, Union

import httpx

from ._http import HttpSession
from ._log import get_logger
from ._util import to_file_tuple
from .exceptions import (
    APIError,
    AuthError,
    SchemaDesignNotPermittedError,
    SchemaWriteUncertainError,
)
from .jobs import JobHandle, JobStatus
from .models import (
    Capabilities,
    DataflowContents,
    DataflowInfo,
    DatasetSchema,
    ExportResult,
    FieldType,
    JobRecord,
    OperationEvidence,
    ReferenceDataset,
    Reporter,
    ReportingDataset,
    RuleSet,
    TableSchema,
    TestDataset,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from ._auth import TokenAuth, TokenPair
    from .dataflow import DataflowClient


PRODUCTION_URL = "https://api.reportnet.europa.eu"
# The sandbox *API* host. `sandbox.reportnet.europa.eu` is the web app and
# answers API paths with text/html (verified 2026-11-12, dataflow 11468).
SANDBOX_URL = "https://sandbox-api.reportnet.europa.eu"


class ReportnetClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = PRODUCTION_URL,
        timeout: float = 60.0,
        *,
        auth: "TokenAuth | None" = None,
    ) -> None:
        """Args:
            api_key: A Reportnet API key. Enough for reporting work.
            timeout: HTTP request timeout in seconds. The default is generous
                because GET /dataflow/v1/{id} is slow on large dataflows —
                30s was low enough to ReadTimeout on one measured live, and a
                timeout there also breaks every method that reads it. Raise it
                further for very large dataflows.
            auth: A login token instead of an API key; prefer
                :meth:`from_tokens`. Needed for schema design.
        """
        self._auth = auth
        self._http = HttpSession(api_key=api_key, base_url=base_url, timeout=timeout, auth=auth)
        # bigData-ness is immutable for a given dataflow, so this is safe to keep
        # for the lifetime of the client. Shared with DataflowClient, which
        # delegates rather than keeping a second copy.
        self._big_data_cache: dict[int, bool] = {}
        # A key's role never changes, so this is safe for the client's lifetime.
        self._capabilities_cache: dict[int, Capabilities] = {}
        self._evidence: dict[tuple[object, ...], OperationEvidence] = {}

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

    @classmethod
    def from_tokens(
        cls,
        access_token: str,
        refresh_token: str,
        *,
        sandbox: bool = False,
        base_url: str | None = None,
        timeout: float = 60.0,
        on_refresh: "Callable[[TokenPair], None] | None" = None,
    ) -> "ReportnetClient":
        """Create a client that authenticates with a **login token**.

        Schema design needs this: API keys get 403 on every schema write
        (verified on sandbox dataflow 11468, 2026-11-12). The client renews the
        access token itself before it expires, and once more if a request is
        refused as unauthenticated.

        Copy both tokens from the Reportnet web app while you are logged in:
        browser DevTools → Application → Session storage → ``reportnet_03``.

        The refresh token rotates on every renewal. Pass *on_refresh* to store
        the newest pair, or read :attr:`tokens` before the program exits.

        Example::

            client = ReportnetClient.from_tokens(
                access_token=..., refresh_token=..., sandbox=True)
            flow = client.for_dataflow(11468)
        """
        from ._auth import TokenAuth
        if base_url is None:
            base_url = SANDBOX_URL if sandbox else PRODUCTION_URL
        auth = TokenAuth(
            access_token, refresh_token, base_url=base_url, on_refresh=on_refresh
        )
        return cls(base_url=base_url, timeout=timeout, auth=auth)

    @classmethod
    def from_credentials(
        cls,
        username: str,
        password: str,
        *,
        sandbox: bool = False,
        base_url: str | None = None,
        timeout: float = 60.0,
        on_refresh: "Callable[[TokenPair], None] | None" = None,
    ) -> "ReportnetClient":
        """Log in with a Reportnet username and password. **Experimental.**

        Calls ``POST /user/generateToken``, the endpoint the web app uses. It
        has not been tested live, and it probably does not work for EU Login
        accounts. Prefer :meth:`from_tokens`.

        **Risk:** the endpoint takes the password as a URL query parameter, so
        it can appear in proxy or gateway logs between you and Reportnet. The
        library masks it in its own logs and in httpx's.

        Example::

            client = ReportnetClient.from_credentials("me", getpass(), sandbox=True)
        """
        from ._auth import GENERATE_PATH, request_tokens
        if base_url is None:
            base_url = SANDBOX_URL if sandbox else PRODUCTION_URL
        pair = request_tokens(
            base_url, GENERATE_PATH, {"username": username, "password": password},
            timeout=timeout,
        )
        return cls.from_tokens(
            pair.access_token, pair.refresh_token, base_url=base_url,
            timeout=timeout, on_refresh=on_refresh,
        )

    @property
    def auth_kind(self) -> Literal["api_key", "bearer"]:
        """``"api_key"`` or ``"bearer"`` (a login token)."""
        return "bearer" if self._auth is not None else "api_key"

    @property
    def tokens(self) -> "TokenPair | None":
        """The current login-token pair, or None for an API-key client.

        Read this to store the newest refresh token; it rotates on each renewal.
        """
        return self._auth.tokens if self._auth is not None else None

    def refresh_tokens(self) -> "TokenPair":
        """Renew the login token now (``POST /user/refreshToken``).

        Not normally needed: the client renews it before it expires.
        """
        if self._auth is None:
            raise TypeError("This client uses an API key; there is no token to refresh.")
        return self._auth.refresh()

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

        A 403 is **not** treated as a bad key. Reporter-scoped keys are
        forbidden from ``GET /dataflow/v1/{id}`` while being perfectly valid
        for the endpoints they do own — verified live on
        dataflow 2003, where a Reporter key 403s here yet imports
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

    def capabilities(self, *, dataflow_id: int, refresh: bool = False) -> Capabilities:
        """Probe what this API key is allowed to do on *dataflow_id*.

        Reportnet has no endpoint reporting a key's role, and the role changes
        how requests must be *built* — a Reporter key must send
        ``providerId`` on BigData writes, a custodian key is refused if it
        does. So the library probes: at most two cheap GETs, cached per client.

        Example::

            caps = client.capabilities(dataflow_id=2003)
            print(caps.summary())
            # "dataflow 2003: reporter key; reads must be provider-scoped"
        """
        if refresh:
            self._capabilities_cache.pop(dataflow_id, None)
        cached = self._capabilities_cache.get(dataflow_id)
        if cached is not None:
            return cached

        from .exceptions import AuthError, LoginTokenError

        can_read_dataflow = False
        can_read_representatives = False
        try:
            self.get_dataflow_contents(dataflow_id=dataflow_id)
            can_read_dataflow = True
            can_read_representatives = True  # custodian keys can read both
        except LoginTokenError:
            raise  # a dead token pair says nothing about the role
        except AuthError:
            try:
                self._http.get(f"/representative/v1/dataflow/{dataflow_id}")
                can_read_representatives = True
            except LoginTokenError:
                raise
            except AuthError:
                pass

        caps = Capabilities(
            dataflow_id=dataflow_id,
            can_read_dataflow=can_read_dataflow,
            can_read_representatives=can_read_representatives,
            auth_kind=self.auth_kind,
        )
        logger.info("capabilities: %s", caps.summary())
        self._capabilities_cache[dataflow_id] = caps
        return caps

    # ── Dataflow metadata ─────────────────────────────────────────────────────

    def get_dataflow_contents(
        self, *, dataflow_id: int, provider_id: int | None = None
    ) -> DataflowContents:
        """GET /dataflow/v1/{dataflowId} — the whole payload, parsed in one pass.

        ``get_dataflow``, ``get_reporting_datasets``, ``get_reference_datasets``
        and ``get_test_datasets`` each read this same endpoint, so calling them
        individually costs one HTTP round-trip each. Use this when you need more
        than one of them.

        Reporter-scoped keys are refused without ``provider_id`` and permitted
        with it, receiving only their own reporting datasets. Custodian keys
        read the whole dataflow without it.

        Example::

            contents = client.get_dataflow_contents(dataflow_id=1619)
            contents.info.name
            contents.reporting_datasets
        """
        params = {"providerId": provider_id} if provider_id is not None else None
        try:
            response = self._http.get(f"/dataflow/v1/{dataflow_id}", params=params)
        except Exception as exc:
            self._record_evidence("discovery", dataflow_id=dataflow_id,
                                  provider_id=provider_id,
                                  request_accepted=False if isinstance(exc, APIError) else None,
                                  detail=f"Request failed: {type(exc).__name__}")
            raise
        self._record_evidence("discovery", dataflow_id=dataflow_id,
                              provider_id=provider_id, request_accepted=True,
                              detail="HTTP accepted; provider ownership not independently checked")
        contents = DataflowContents.from_dict(response.json())
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

    def get_dataflow_metabase(self, *, dataflow_id: int) -> DataflowInfo:
        """GET /dataflow/v1/{dataflowId}/getmetabase — dataflow metadata only.

        Returns the same fields as :meth:`get_dataflow` but **without** any
        dataset lists (the API nulls them here). Its value is that reporter
        keys may read it, while ``GET /dataflow/v1/{id}`` is 403 for them — so
        it is how a reporter learns the dataflow's name, status and backend.
        """
        response = self._http.get(f"/dataflow/v1/{dataflow_id}/getmetabase")
        return DataflowInfo.from_dict(response.json())

    def get_import_statistics(self, *, dataset_id: int, dataflow_id: int) -> dict[str, Any]:
        """GET /dataset/getImportRelatedStatistics/{datasetId} — what landed.

        Returns a mapping of **table schema id** to
        ``{"lastImportDate", "numberOfRecordsImported", "fileExtension"}``,
        with nulls for tables never imported into.

        This is the only way a reporter-scoped key can confirm an import
        actually wrote data: exports are forbidden to them, and a FINISHED job
        is not evidence that data landed. Use
        :meth:`DataflowClient.verify_import <reportnet.DataflowClient.verify_import>`
        for a table-name-friendly wrapper.

        Example::

            stats = client.get_import_statistics(dataset_id=108953, dataflow_id=2003)
            stats["6a4504d0bde8560001232b6d"]
            # {'lastImportDate': 1788769100000, 'numberOfRecordsImported': 1,
            #  'fileExtension': 'csv'}
        """
        response = self._http.get(
            f"/dataset/getImportRelatedStatistics/{dataset_id}",
            params={"dataflowId": dataflow_id},
        )
        return response.json()  # type: ignore[no-any-return]

    def is_big_dataflow(self, *, dataflow_id: int) -> bool:
        """Return True if *dataflow_id* is a BigData (DLT2) dataflow.

        Reads the ``bigData`` field from GET /dataflow/v1/{dataflowId}. The
        dedicated GET /dataflow/private/v1/{dataflowId}/isBigDataflow endpoint
        looks purpose-built for this but 404s for API-key auth regardless of
        the dataflow's actual BigData status, so it isn't used here.

        Reporter-scoped keys are 403 on that endpoint, so this falls back to
        ``getmetabase``, which they *can* read and which carries the same
        ``bigData`` field. That makes backend detection work for every key.

        Cached per client — a dataflow never changes backend.
        """
        from .exceptions import AuthError, LoginTokenError

        cached = self._big_data_cache.get(dataflow_id)
        if cached is not None:
            return cached
        try:
            cached = self.get_dataflow_contents(dataflow_id=dataflow_id).info.big_data
        except LoginTokenError:
            raise
        except AuthError:
            logger.debug(
                "dataflow %s not readable; reading bigData from getmetabase instead",
                dataflow_id,
            )
            cached = self.get_dataflow_metabase(dataflow_id=dataflow_id).big_data
            self._big_data_cache[dataflow_id] = cached
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
        v5 (analytics, opt-in): result is a ZIP of partitioned Parquet files.
        Size and speed depend on the data; never selected automatically, pass
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

        evidence: dict[str, Any] = dict(dataflow_id=dataflow_id, dataset_id=dataset_id,
                        provider_id=provider_id, version=version,
                        table_schema_id=table_schema_id, data_provider_codes=data_provider_codes)
        try:
            response = self._http.get(f"/dataset/v{version}/etlExport/{dataset_id}", params=params)
        except Exception as exc:
            self._record_evidence("etl_export", **evidence,
                                  request_accepted=False if isinstance(exc, APIError) else None,
                                  detail=f"Request failed: {type(exc).__name__}")
            raise
        self._record_evidence("etl_export", **evidence, request_accepted=True,
                              detail="Export request accepted; payload not checked")
        handle = _make_job(response.json(), self._http, is_export=True, provider_id=provider_id)
        handle._on_verification = lambda report: self._record_evidence(
            "etl_export", **evidence, request_accepted=True,
            payload_verified=report.ok, detail=report.summary(),
        )
        return handle

    def export_frames(
        self, *, dataset_id: int, dataflow_id: int,
        provider_id: int | None = None, data_provider_codes: str | None = None,
        table_schema_id: str | None = None, version: int | None = None,
        strict: bool = True, poll_interval: float = 5.0, timeout: float | None = None,
        on_status: Callable[[JobStatus], None] | None = None,
    ) -> ExportResult:
        """Export and check table/column coverage against a fresh dataset schema.

        Raises ExportVerificationError by default. With strict=False, mismatches
        warn AND log, and the returned result retains every frame plus the report.
        Empty tables are reported; structural success does not prove useful data.
        Raw etl_export().result()/to_frames() remain unchecked alternatives.
        """
        schema = self.get_schema(dataset_id=dataset_id)
        if table_schema_id is not None and not any(t.id == table_schema_id for t in schema.tables):
            raise ValueError(f"Table schema {table_schema_id!r} is not in dataset {dataset_id}")
        handle = self.etl_export(
            dataset_id=dataset_id, dataflow_id=dataflow_id, provider_id=provider_id,
            data_provider_codes=data_provider_codes, table_schema_id=table_schema_id,
            version=version,
        )
        return handle.to_verified_frames(
            schema=schema, dataset_id=dataset_id, table_schema_id=table_schema_id,
            strict=strict, poll_interval=poll_interval, timeout=timeout, on_status=on_status,
        )

    def permission_evidence(self, *, dataflow_id: int) -> tuple[OperationEvidence, ...]:
        """Return observations for this client/key, without probing or starting jobs.

        Absent operations are unknown. Entries do not carry over to other keys,
        datasets, versions, filters or provider scopes. This is latest evidence,
        not a complete audit log or a promise that the next request will work.
        """
        return tuple(e for e in self._evidence.values() if e.dataflow_id == dataflow_id)

    def _record_evidence(
        self, operation: str, *, dataflow_id: int, dataset_id: int | None = None,
        provider_id: int | None = None, version: int | None = None,
        table_schema_id: str | None = None, data_provider_codes: str | None = None,
        request_accepted: bool | None = None, payload_verified: bool | None = None,
        workflow_verified: bool | None = None, detail: str = "",
    ) -> None:
        key = (operation, dataflow_id, dataset_id, provider_id, version,
               table_schema_id, data_provider_codes)
        self._evidence[key] = OperationEvidence(
            operation, dataflow_id, dataset_id, provider_id, version, table_schema_id,
            datetime.now(timezone.utc).isoformat(), request_accepted, payload_verified,
            workflow_verified, detail, data_provider_codes,
        )

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

    def list_jobs(
        self,
        *,
        dataflow_id: int,
        dataset_id: int | None = None,
        job_type: str | None = None,
        provider_id: int | None = None,
        page_size: int = 100,
    ) -> list[JobRecord]:
        """GET /orchestrator/jobs — job history, newest first.

        The only source of run provenance: the validation listing itself
        carries no timestamp or run id.
        """
        params: dict[str, object] = {"dataflowId": dataflow_id, "pageSize": page_size}
        if dataset_id is not None:
            params["datasetId"] = dataset_id
        if job_type is not None:
            params["jobType"] = job_type
        if provider_id is not None:
            params["providerId"] = provider_id
        payload = self._http.get("/orchestrator/jobs", params=params).json()
        return [JobRecord.from_dict(j) for j in payload.get("jobsList") or []]

    def get_schema(self, *, dataset_id: int) -> DatasetSchema:
        """GET /dataschema/v1/datasetId/{datasetId} — table and field definitions."""
        response = self._http.get(f"/dataschema/v1/datasetId/{dataset_id}")
        return DatasetSchema.from_dict(response.json())

    # ── Schema design (custodian; login token only) ────────────────────────────
    #
    # Verified on sandbox dataflow 11468, 2026-11-12. Every write below is
    # refused (403) with an API key, so each one checks the credential first.
    # Writes are never retried, and a 5xx becomes SchemaWriteUncertainError:
    # a failed field update was seen to save its change anyway.

    def _require_login_token(self, operation: str) -> None:
        if self._auth is None:
            raise SchemaDesignNotPermittedError(operation)

    def _schema_write(
        self, method: str, url: str, operation: str, **kwargs: Any
    ) -> httpx.Response:
        self._require_login_token(operation)
        try:
            return self._http._request(method, url, **kwargs)
        except AuthError:
            raise
        except APIError as exc:
            if exc.status_code >= 500:
                raise SchemaWriteUncertainError(
                    exc.status_code, exc.response_body, operation
                ) from exc
            raise

    def create_empty_dataset_schema(self, *, dataflow_id: int, name: str) -> None:
        """POST /dataschema/createEmptyDatasetSchema — add a design dataset.

        The response body is empty: the new dataset's id is not returned. Find
        it in ``designDatasets`` afterwards, or use
        :meth:`DataflowClient.create_design_dataset
        <reportnet.DataflowClient.create_design_dataset>`, which does that.
        """
        self._schema_write(
            "POST", "/dataschema/createEmptyDatasetSchema", "create_empty_dataset_schema",
            params={"dataflowId": dataflow_id, "datasetSchemaName": name},
        )

    def get_dataset_metabase(self, *, dataset_id: int) -> dict[str, Any]:
        """GET /datasetmetabase/{datasetId} — dataset name, dataflow and schema id."""
        return self._http.get(f"/datasetmetabase/{dataset_id}").json()  # type: ignore[no-any-return]

    def update_dataset_name(self, *, dataset_id: int, name: str) -> None:
        """PUT /datasetmetabase/updateDatasetName — rename a design dataset.

        Renames both the dataset and its schema (``nameDatasetSchema``).
        """
        self._schema_write(
            "PUT", "/datasetmetabase/updateDatasetName", "update_dataset_name",
            params={"datasetId": dataset_id, "datasetName": name},
        )

    def update_dataset_schema(self, *, dataset_id: int, description: str) -> None:
        """PUT /dataschema/{datasetId}/datasetSchema — set the dataset description."""
        self._schema_write(
            "PUT", f"/dataschema/{dataset_id}/datasetSchema", "update_dataset_schema",
            json={"description": description},
        )

    def create_table_schema(
        self, *, dataset_id: int, name: str, not_empty: bool = False, **props: Any
    ) -> TableSchema:
        """POST /dataschema/{datasetId}/tableSchema — add a table.

        Returns the new table, including :attr:`TableSchema.record_id`, which
        is what :meth:`create_field_schema` needs. Other table properties
        (``description``, ``read_only``, ``to_prefill``, ``fixed_number``,
        ``data_manually_editable``) can be passed as keywords.

        The API accepts a duplicate name; check first.

        Example::

            table = client.create_table_schema(dataset_id=48097, name="Sites",
                                               not_empty=True)
        """
        body = {"nameTableSchema": name, "notEmpty": not_empty, **_table_body(props)}
        r = self._schema_write(
            "POST", f"/dataschema/{dataset_id}/tableSchema", "create_table_schema", json=body
        )
        return TableSchema.from_dict(r.json())

    def update_table_schema(
        self, *, dataset_id: int, table_schema_id: str, **props: Any
    ) -> None:
        """PUT /dataschema/{datasetId}/tableSchema — change table properties.

        A partial body is accepted here (unlike fields). Keywords: ``name``,
        ``description``, ``not_empty``, ``read_only``, ``to_prefill``,
        ``fixed_number``, ``data_manually_editable``.

        Example::

            client.update_table_schema(dataset_id=48097, table_schema_id=tid,
                                       name="Sites2")
        """
        if not props:
            raise ValueError("Pass at least one table property to change.")
        body = {"idTableSchema": table_schema_id, **_table_body(props)}
        self._schema_write(
            "PUT", f"/dataschema/{dataset_id}/tableSchema", "update_table_schema", json=body
        )

    def order_table_schema(
        self, *, dataset_id: int, table_schema_id: str, position: int
    ) -> None:
        """PUT /dataschema/{datasetId}/tableSchema/order — move a table (0-based)."""
        self._schema_write(
            "PUT", f"/dataschema/{dataset_id}/tableSchema/order", "order_table_schema",
            json={"id": table_schema_id, "position": position},
        )

    def delete_table_schema(self, *, dataset_id: int, table_schema_id: str) -> None:
        """DELETE /dataschema/{datasetId}/tableSchema/{id} — delete a table. No undo."""
        self._schema_write(
            "DELETE", f"/dataschema/{dataset_id}/tableSchema/{table_schema_id}",
            "delete_table_schema",
        )

    def create_field_schema(
        self,
        *,
        dataset_id: int,
        record_id: str,
        name: str,
        type: FieldType | str,
        description: str = "",
        required: bool = False,
        pk: bool = False,
        read_only: bool = False,
        codelist_items: Sequence[str] = (),
        referenced_field: Mapping[str, str] | None = None,
        max_size: int | None = None,
    ) -> str:
        """POST /dataschema/{datasetId}/fieldSchema — add a field; returns its id.

        *record_id* is the table's :attr:`TableSchema.record_id`
        (``recordSchema.idRecordSchema``), **not** the table id. The new id
        comes back as ``text/plain``.

        For a LINK field pass ``referenced_field={"idDatasetSchema": ...,
        "idPk": ...}``: the schema id of the dataset holding the primary key,
        and the primary-key field's id.

        Example::

            fid = client.create_field_schema(dataset_id=48097, record_id=rid,
                                             name="SiteCode", type="TEXT",
                                             pk=True, required=True)
        """
        body: dict[str, Any] = {
            "codelistItems": list(codelist_items),
            "description": description,
            "maxSize": max_size,
            "name": name,
            "pk": pk,
            "readOnly": read_only,
            "referencedField": dict(referenced_field) if referenced_field else None,
            "required": required,
            "type": FieldType(type).value,
            "idRecord": record_id,
        }
        r = self._schema_write(
            "POST", f"/dataschema/{dataset_id}/fieldSchema", "create_field_schema", json=body
        )
        return r.text.strip().strip('"')

    def update_field_schema(self, *, dataset_id: int, payload: Mapping[str, Any]) -> None:
        """PUT /dataschema/{datasetId}/fieldSchema — replace a field definition.

        Send the **whole** field. A partial body answered HTTP 500 on the
        sandbox *and still saved the change*. Build *payload* with
        :meth:`FieldSchema.to_update_payload`, which starts from the field as
        read and changes only what you name.

        Example::

            field = client.get_schema(dataset_id=48097).table("Sites").field("SiteCode")
            client.update_field_schema(
                dataset_id=48097, payload=field.to_update_payload(description="Site code"))
        """
        missing = [k for k in ("id", "idRecord", "name", "type") if k not in payload]
        if missing:
            raise ValueError(
                f"update_field_schema needs the whole field; missing {missing}. "
                "Use FieldSchema.to_update_payload()."
            )
        self._schema_write(
            "PUT", f"/dataschema/{dataset_id}/fieldSchema", "update_field_schema",
            json=dict(payload),
        )

    def order_field_schema(
        self, *, dataset_id: int, field_schema_id: str, position: int
    ) -> None:
        """PUT /dataschema/{datasetId}/fieldSchema/order — move a field in its table (0-based)."""
        self._schema_write(
            "PUT", f"/dataschema/{dataset_id}/fieldSchema/order", "order_field_schema",
            json={"id": field_schema_id, "position": position},
        )

    def delete_field_schema(self, *, dataset_id: int, field_schema_id: str) -> None:
        """DELETE /dataschema/{datasetId}/fieldSchema/{id} — delete a field. No undo."""
        self._schema_write(
            "DELETE", f"/dataschema/{dataset_id}/fieldSchema/{field_schema_id}",
            "delete_field_schema",
        )

    def export_table_definition(
        self, *, dataset_schema_id: str, dataset_id: int, table_schema_id: str
    ) -> str:
        """GET …/exportFieldSchemas — one table's field definitions as CSV text.

        Columns: ``Field name, PK, Required, ReadOnly, Field description,
        Field type, Extra information``; code-list items are joined with ``;``
        in the last column.
        """
        r = self._http.get(
            f"/dataschema/v1/{dataset_schema_id}/exportFieldSchemas",
            params={"datasetId": dataset_id, "tableSchemaId": table_schema_id,
                    "mimeType": "csv"},
        )
        return r.content.decode("utf-8-sig")

    def export_schema_definitions(self, *, dataset_id: int) -> bytes:
        """GET /dataschema/v1/dataset/{datasetId}/exportFieldSchemas — every table, as a ZIP.

        Note the path takes the numeric dataset id; a schema id answers 400.
        """
        return self._http.get(f"/dataschema/v1/dataset/{dataset_id}/exportFieldSchemas").content

    def list_schemas(self, *, dataflow_id: int) -> list[DatasetSchema]:
        """GET /dataschema/getSchemas/dataflow/{id} — every schema in a dataflow.

        The items carry no dataset id; join on :attr:`DatasetSchema.id` and
        :attr:`DesignDataset.schema_id`. Login token only (403 for API keys).
        """
        self._require_login_token("list_schemas")
        r = self._http.get(f"/dataschema/getSchemas/dataflow/{dataflow_id}")
        return [DatasetSchema.from_dict(d) for d in r.json()]

    def validate_schemas(self, *, dataflow_id: int) -> bool:
        """GET /dataschema/validate/dataflow/{id} — True if every schema is valid."""
        r = self._http.get(f"/dataschema/validate/dataflow/{dataflow_id}")
        return r.text.strip().lower() == "true"

    def count_table_records(self, *, dataset_id: int, table_schema_id: str) -> int:
        """Number of records in one table of a **BigData** dataset.

        Reads ``totalRecords`` from ``GET /dataset/TableValueDatasetDL/{id}``
        with a page size of 1 — the call the web app makes per table. Verified
        on a BigData sandbox dataflow only; Citus datasets have no ``DL`` route.
        """
        r = self._http.get(
            f"/dataset/TableValueDatasetDL/{dataset_id}",
            params={"idTableSchema": table_schema_id, "pageNum": 0, "pageSize": 1,
                    "fieldValue": "", "levelError": "CORRECT,INFO,WARNING,ERROR,BLOCKER"},
        )
        return int(r.json().get("totalRecords") or 0)

    # ── QC rules (custodian; login token only) ────────────────────────────────
    # Verified on sandbox dataflow 11468, 2026-11-13 (notes/api-notes.md, "QC
    # rules"). Writes go through _schema_write: never retried, 5xx →
    # SchemaWriteUncertainError. Bodies use the API's own keys; see
    # RuleDefinition.to_body().

    def get_rules(self, *, schema_id: str, dataflow_id: int) -> RuleSet:
        """GET /rules/{schemaId}/dataflow/{dataflowId} — every QC rule of a schema.

        Lists automatic and manual rules. *schema_id* is
        :attr:`DesignDataset.schema_id`, not the dataset id.
        """
        self._require_login_token("get_rules")
        r = self._http.get(f"/rules/{schema_id}/dataflow/{dataflow_id}")
        return RuleSet.from_dict(r.json())

    def create_rule(self, *, dataset_id: int, body: Mapping[str, Any]) -> None:
        """PUT /rules/createNewRule — add a rule (yes, PUT).

        The answer is empty: no rule id is returned. Find the rule afterwards
        by its ``shortCode`` in :meth:`get_rules`.
        """
        self._schema_write("PUT", "/rules/createNewRule", "create_rule",
                           params={"datasetId": dataset_id}, json=dict(body))

    def update_rule(self, *, dataset_id: int, body: Mapping[str, Any]) -> None:
        """PUT /rules/updateRule — replace a rule; also how it is enabled or disabled.

        Send the whole body, with ``ruleId``
        (:meth:`RuleDefinition.to_body <reportnet.RuleDefinition.to_body>`).
        """
        self._schema_write("PUT", "/rules/updateRule", "update_rule",
                           params={"datasetId": dataset_id}, json=dict(body))

    def delete_rule(self, *, dataset_id: int, rule_id: str) -> None:
        """DELETE /rules/deleteRule — remove a rule.

        ``datasetId`` is the numeric **dataset** id. The schema id, which the
        web-app code suggests, answers 400 (sandbox, 2026-11-13).
        """
        self._schema_write("DELETE", "/rules/deleteRule", "delete_rule",
                           params={"datasetId": dataset_id, "ruleId": rule_id})

    def evaluate_sql_rule(self, *, dataset_id: int, sql: str) -> float | None:
        """POST /rules/evaluateSqlRule — Reportnet's cost estimate for *sql*.

        **Not a validity check:** it answered ``0.0`` for valid and invalid SQL
        alike (sandbox, 2026-11-13). To find invalid rules, run
        :meth:`validate_sql_rules` and read ``verified`` and ``sqlError``.
        """
        self._require_login_token("evaluate_sql_rule")
        r = self._http.post("/rules/evaluateSqlRule", params={"datasetId": dataset_id},
                            json={"sqlRule": sql})
        text = r.text.strip()
        return float(text) if text else None

    def run_sql_rule(
        self, *, dataset_id: int, sql: str, show_internal_fields: bool = False,
        provider_code: str | None = None,
    ) -> Any:
        """POST /rules/runSqlRule — test-run *sql* and return the first rows.

        The server wraps the query (``… as userSelect LIMIT 10``). Pass
        *provider_code* to run it as that data provider. It reads; it does not
        change rules or data.
        """
        self._require_login_token("run_sql_rule")
        params: dict[str, Any] = {"datasetId": dataset_id,
                                  "showInternalFields": str(show_internal_fields).lower()}
        if provider_code is not None:
            params["runSQLAsProvider"] = provider_code
        r = self._http.post("/rules/runSqlRule", params=params, json={"sqlRule": sql})
        return r.json() if r.text.strip() else None

    def validate_sql_rules(self, *, dataset_id: int, schema_id: str) -> None:
        """POST /rules/validateSqlRules — re-check every SQL rule of a dataset.

        Afterwards each rule's ``verified`` (and ``sqlError``) is set; a new
        rule is ``verified: null`` until this has run. The answer is empty.
        """
        self._schema_write("POST", "/rules/validateSqlRules", "validate_sql_rules",
                           params={"datasetId": dataset_id, "datasetSchemaId": schema_id})

    def get_rule_history(self, *, dataset_id: int, rule_id: str) -> list[dict[str, Any]]:
        """GET /rules/historicInfo — earlier versions of a rule.

        Answered ``[]`` on the sandbox even after three updates (2026-11-13).
        """
        self._require_login_token("get_rule_history")
        r = self._http.get("/rules/historicInfo",
                           params={"datasetId": dataset_id, "ruleId": rule_id})
        return list(r.json() or [])

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


# Python keyword → wire name for table properties.
_TABLE_PROPS = {
    "name": "nameTableSchema",
    "description": "description",
    "not_empty": "notEmpty",
    "read_only": "readOnly",
    "to_prefill": "toPrefill",
    "fixed_number": "fixedNumber",
    "data_manually_editable": "dataAreManuallyEditable",
}


def _table_body(props: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(props) - set(_TABLE_PROPS)
    if unknown:
        raise TypeError(
            f"Unknown table properties {sorted(unknown)}; known: {sorted(_TABLE_PROPS)}"
        )
    return {_TABLE_PROPS[k]: v for k, v in props.items()}


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
