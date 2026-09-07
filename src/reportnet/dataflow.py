"""Dataflow-scoped convenience layer.

Layering rule (see also :mod:`reportnet.client`): this class owns *scoping*
only — deciding which IDs get filled in when the caller omits them. Every quirk
of an endpoint itself (URL shape, parameter names, API version selection) lives
one level down in :class:`~reportnet.ReportnetClient`, so the two layers can
never disagree about how to talk to the API.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import IO, TYPE_CHECKING, Callable, Literal, Union

from ._log import get_logger
from .exceptions import (
    AuthError,
    CodelistResolutionError,
    DiscoveryNotPermittedError,
    ReportnetError,
)
from .jobs import JobHandle, JobStatus
from .models import (
    Capabilities,
    DataflowContents,
    DataflowInfo,
    DatasetSchema,
    ReferenceDataset,
    Reporter,
    ReportingDataset,
    TestDataset,
    ValidationResult,
)

if TYPE_CHECKING:
    from ._util import CodelistResolution
    from .client import ReportnetClient

logger = get_logger(__name__)


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
        ie = df.for_provider(17)
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
        country_code: str | None = None,
    ) -> None:
        self._client = client
        self._dataflow_id = dataflow_id
        self._provider_id = provider_id
        self._country_code = country_code

    def _pid(self, override: int | None) -> int | None:
        """Return override if given, else fall back to the stored provider_id."""
        return override if override is not None else self._provider_id

    def _pid_bigdata_safe(self, override: int | None) -> int | None:
        """Like :meth:`_pid`, but decides whether BigData wants providerId.

        **Whether BigData accepts or requires ``providerId`` depends on the
        key's role, not on the backend.** Both directions are confirmed live on
        dataflow 2003:

        =====================  ==========================================
        Key role               ``importFileData`` on BigData
        =====================  ==========================================
        Custodian-level        ``providerId`` present  -> 403
        Reporter          ``providerId`` absent   -> 403 (job 248505
                               succeeded once it was sent)
        =====================  ==========================================

        There is no endpoint that reports the key's role, so this uses the
        best available proxy: whether the key may read ``GET /dataflow/v1/{id}``.
        A custodian-level key can; a reporter-scoped key is 403'd there. So a
        refused backend lookup is itself the signal that this is a reporter
        key, and reporter keys are the ones that *need* providerId.

        The proxy can be wrong, so callers that can safely retry — see
        :meth:`import_file` — flip the choice once on a 403 rather than
        treating it as fatal.
        """
        if override is not None:
            return override
        if self._provider_id is None:
            return None
        if self.capabilities().wants_provider_id:
            logger.debug(
                "reporter-scoped key on dataflow %s; sending providerId=%s",
                self._dataflow_id, self._provider_id,
            )
            return self._provider_id
        return None if self.is_big_dataflow() else self._provider_id

    def for_provider(self, provider_id: int) -> "DataflowClient":
        """Return a new DataflowClient scoped to a specific reporter / country.

        Example::

            df = client.for_dataflow(1619)
            ie = df.for_provider(17)   # Ireland's provider ID
            ie.import_file(dataset_id=93953, file="ireland.csv")
        """
        return DataflowClient(self._client, self._dataflow_id, provider_id=provider_id)

    def find_reporter(self, country_code: str) -> "DataflowClient":
        """Return a DataflowClient scoped to a reporter identified by ISO country code.

        Looks up the reporter in the dataflow and returns a scoped client in
        one step — no need to know the numeric ``provider_id`` in advance.

        Raises :class:`ValueError` if no reporter matches the country code, or
        if multiple reporters are registered for the same code (use
        :meth:`get_reporters` to inspect them and call :meth:`for_provider`
        with the correct ``provider_id``).

        Args:
            country_code: ISO 3166-1 alpha-2 code, e.g. ``"IE"``, ``"DE"``.

        Returns:
            A :class:`DataflowClient` scoped to that reporter's ``provider_id``.

        Example::

            ie = flow.find_reporter("IE")
            datasets = ie.get_reporting_datasets()
            # [ReportingDataset(id=93953, table_name='Table1a', ...)]
            ie.import_file(dataset_id=datasets[0].id, file="ireland.csv")
        """
        reporters = self.get_reporters()
        code = country_code.upper()
        matches = [r for r in reporters if r.country_code == code]
        if not matches:
            available = sorted({r.country_code for r in reporters if r.country_code})
            raise ValueError(
                f"No reporter found for country code {code!r}. "
                f"Available countries: {available}"
            )
        if len(matches) > 1:
            ids = [r.provider_id for r in matches]
            raise ValueError(
                f"Multiple reporters for {code!r} (provider_ids: {ids}). "
                f"Use get_reporters() to pick one, then for_provider()."
            )
        return DataflowClient(
            self._client, self._dataflow_id,
            provider_id=matches[0].provider_id,
            country_code=code,
        )

    # ── Dataflow metadata ─────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Return True if the API key is valid and the API is reachable."""
        return self._client.ping(dataflow_id=self._dataflow_id)

    def get_dataflow_contents(self) -> DataflowContents:
        """Return the whole GET /dataflow/v1/{dataflowId} payload in one request.

        ``get_dataflow``, ``get_reporting_datasets``, ``get_reference_datasets``
        and ``get_test_datasets`` all read this same endpoint — reach for this
        when you need more than one of them, to avoid repeating the round-trip.

        Custodian keys read the whole dataflow. Reporter keys are refused
        unless ``providerId`` is sent, and then receive only their own
        reporting datasets, so a provider-scoped client (via
        :meth:`for_provider` or :meth:`find_reporter`) is required for them.
        This method sends the stored ``provider_id`` automatically if the
        unscoped read is refused.

        Example::

            contents = flow.get_dataflow_contents()
            print(contents.info.name)
            print(len(contents.reporting_datasets), "reporting datasets")
        """
        try:
            return self._client.get_dataflow_contents(dataflow_id=self._dataflow_id)
        except DiscoveryNotPermittedError:
            raise
        except AuthError as exc:
            if self._provider_id is None:
                raise DiscoveryNotPermittedError(
                    exc.status_code, self._discovery_hint()
                ) from exc
            logger.debug(
                "dataflow %s not readable unscoped; retrying with providerId=%s",
                self._dataflow_id, self._provider_id,
            )
            try:
                return self._client.get_dataflow_contents(
                    dataflow_id=self._dataflow_id, provider_id=self._provider_id
                )
            except AuthError as scoped_exc:
                raise DiscoveryNotPermittedError(
                    scoped_exc.status_code, self._discovery_hint()
                ) from scoped_exc

    def capabilities(self) -> Capabilities:
        """Return what this API key may do on this dataflow. See
        :meth:`ReportnetClient.capabilities <reportnet.ReportnetClient.capabilities>`."""
        return self._client.capabilities(dataflow_id=self._dataflow_id)

    def _discovery_hint(self) -> str:
        """Explain a discovery 403 in terms the caller can act on."""
        if self._provider_id is None:
            return (
                f"Reading dataflow {self._dataflow_id} was refused. Reporter keys must "
                f"identify which provider they are reading for. Scope the client first, "
                f"with find_reporter('XX') or for_provider(id), and retry. Custodian "
                f"keys read the dataflow unscoped."
            )
        return (
            f"Reading dataflow {self._dataflow_id} was refused both unscoped and with "
            f"providerId={self._provider_id}. Check that this key belongs to that "
            f"provider. Operations taking a dataset id directly (get_schema, "
            f"import_file, validate) do not require this call."
        )

    def get_dataflow(self) -> DataflowInfo:
        """Return name, type and status of this dataflow."""
        return self.get_dataflow_contents().info

    def get_reporters(self) -> list[Reporter]:
        """Return the list of countries/organisations registered for this dataflow."""
        return self._client.get_reporters(dataflow_id=self._dataflow_id)

    def get_reporting_datasets(self) -> list[ReportingDataset]:
        """Return reporting datasets for this dataflow.

        When the client is scoped to a provider (via :meth:`for_provider`),
        returns only that provider's datasets.  Otherwise returns all reporters'
        datasets (one per reporter × table schema).

        Example::

            # Scoped — returns only Ireland's datasets
            ie = flow.for_provider(17)
            datasets = ie.get_reporting_datasets()
            # [ReportingDataset(id=93953, table_name='Table1a', ...),
            #  ReportingDataset(id=93954, table_name='Table7', ...)]

            # Unscoped — returns every reporter's datasets
            all_ds = flow.get_reporting_datasets()
        """
        all_ds = list(self.get_dataflow_contents().reporting_datasets)
        if self._provider_id is not None:
            return [ds for ds in all_ds if ds.provider_id == self._provider_id]
        return all_ds

    def dataset(self, table_name: str) -> ReportingDataset:
        """Return this reporter's reporting dataset for *table_name*.

        Reportnet gives each reporter one dataset per table schema, so working
        out "which dataset is Table1a" otherwise means eyeballing list
        positions — `get_reporting_datasets()[1]` and hoping.

        Requires a provider-scoped client (via :meth:`for_provider` or
        :meth:`find_reporter`), since table names repeat across reporters.

        Args:
            table_name: The table name, e.g. ``"Table1a"``. Case-insensitive.

        Returns:
            The matching :class:`~reportnet.ReportingDataset`.

        Raises:
            ValueError: If the client is not scoped to a provider.
            KeyError: If no table of that name exists (the message lists the
                names that do).

        Example::

            ie = flow.find_reporter("IE")
            ds = ie.dataset("Table1a")
            ie.import_file(dataset_id=ds.id, file="ireland.csv")
        """
        if self._provider_id is None:
            raise ValueError(
                "dataset() needs a provider-scoped client, because every reporter has a "
                "dataset with the same table name. Use for_provider(...) or "
                "find_reporter(...) first, or call get_reporting_datasets() directly."
            )
        datasets = self.get_reporting_datasets()
        wanted = table_name.casefold()
        for ds in datasets:
            if ds.table_name.casefold() == wanted:
                return ds
        raise KeyError(
            f"No table named {table_name!r} for provider {self._provider_id}; "
            f"available: {sorted(d.table_name for d in datasets)}"
        )

    def datasets_by_table(self) -> dict[str, ReportingDataset]:
        """Return this reporter's reporting datasets keyed by table name.

        Requires a provider-scoped client — see :meth:`dataset`.

        Example::

            datasets = ie.datasets_by_table()
            # {"Table1a": ReportingDataset(id=93953, ...), "Table7": ...}
        """
        if self._provider_id is None:
            raise ValueError(
                "datasets_by_table() needs a provider-scoped client. "
                "Use for_provider(...) or find_reporter(...) first."
            )
        return {ds.table_name: ds for ds in self.get_reporting_datasets()}

    def reference_dataset(self, name: str) -> ReferenceDataset:
        """Return the reference dataset whose name matches *name*.

        Matches case-insensitively, exactly first and then as a substring, so
        ``flow.reference_dataset("codelist")`` finds
        ``"Reference Dataset - Codelist"``.

        Raises:
            KeyError: If no dataset matches, or if a substring match is
                ambiguous (the message lists the candidates).
        """
        refs = self.get_reference_datasets()
        wanted = name.casefold()
        for ref in refs:
            if ref.name.casefold() == wanted:
                return ref
        partial = [r for r in refs if wanted in r.name.casefold()]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            raise KeyError(
                f"{name!r} matches {len(partial)} reference datasets: "
                f"{sorted(r.name for r in partial)}. Use the full name."
            )
        raise KeyError(
            f"No reference dataset matching {name!r}; available: {sorted(r.name for r in refs)}"
        )

    def get_reference_datasets(self) -> list[ReferenceDataset]:
        """Return all reference datasets for this dataflow.

        Reference datasets hold shared lookup data such as codelists and are
        not tied to any specific reporter.  Use the returned ``id`` values as
        ``ref_dataset_id`` when calling :meth:`get_codelists`.

        Example::

            ref_ds = flow.get_reference_datasets()
            # [ReferenceDataset(id=93975, name='Reference Dataset - Codelist', ...)]
            codelists = flow.get_codelists(dataset_id=93953, ref_dataset_id=ref_ds[0].id)
        """
        return list(self.get_dataflow_contents().reference_datasets)

    def get_test_datasets(self) -> list[TestDataset]:
        """Return all test datasets for this dataflow.

        Test datasets mirror the reporting schema and can be used by custodians
        to verify validation rules before the reporting period opens.

        Example::

            test_ds = flow.get_test_datasets()
            # [TestDataset(id=93953, name='Test Dataset - Table1a', ...)]
            flow.import_file(dataset_id=test_ds[0].id, file="sample.csv")
        """
        return list(self.get_dataflow_contents().test_datasets)

    def is_big_dataflow(self) -> bool:
        """Return True if this is a BigData (DLT2) dataflow.

        Cached on the underlying :class:`~reportnet.ReportnetClient`, so the
        lookup is shared with every other scoped client built from it.
        """
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
        """POST /dataset/v2/importFileData/{datasetId} — multipart upload.

        Whether BigData wants ``providerId`` depends on the key's role, not the
        backend: a custodian-level key is 403'd when it is present, a Reporter
        key when it is absent. :meth:`_pid_bigdata_safe` infers the role, and
        this method **retries once with the opposite choice** if the inference
        was wrong.

        The retry is safe: a 403 means the request was rejected outright, so
        nothing was written and no duplicate can result. Passing
        ``provider_id`` explicitly disables it — an explicit choice is
        honoured, not second-guessed.
        """
        def _send(with_pid: int | None) -> JobHandle:
            return self._client.import_file(
                dataset_id=dataset_id,
                dataflow_id=self._dataflow_id,
                file=file,
                filename=filename,
                provider_id=with_pid,
                table_schema_id=table_schema_id,
                replace=replace,
                delimiter=delimiter,
                integration_id=integration_id,
            )

        return self._send_with_provider_id(
            _send, override=provider_id, what=f"import into dataset {dataset_id}"
        )

    def _send_with_provider_id(
        self,
        send: "Callable[[int | None], JobHandle]",
        *,
        override: int | None,
        what: str,
    ) -> JobHandle:
        """Call *send* with the right ``providerId``, flipping once on a 403.

        Whether Reportnet requires or rejects ``providerId`` depends on the
        key's role, which cannot be queried directly — see
        :meth:`_pid_bigdata_safe`. When the inferred choice is refused, the
        opposite is tried. That is safe because a 403 means the request was
        rejected outright, so nothing happened and no duplicate can result.

        An explicit *override* is honoured and never second-guessed.
        """
        pid = self._pid_bigdata_safe(override)
        try:
            return send(pid)
        except AuthError:
            # Only the auto-filled case is ambiguous enough to retry.
            if override is not None or self._provider_id is None:
                raise
            alternative = None if pid is not None else self._provider_id
            if alternative == pid:
                raise
            logger.warning(
                "%s was refused with providerId=%s; retrying with providerId=%s — "
                "whether Reportnet requires or rejects it depends on the key's role",
                what, pid, alternative,
            )
            return send(alternative)

    def verify_import(self, *, dataset_id: int) -> dict[str, dict[str, object]]:
        """Return what the last import actually wrote, keyed by **table name**.

        A FINISHED job is not evidence that data landed — Reportnet can accept
        a request, run it, report FINISHED and write nothing. This reads
        ``getImportRelatedStatistics`` and joins it to the dataset schema, so
        you get table names instead of schema IDs.

        Works with reporter-scoped keys, which cannot export and therefore have
        no other way to confirm an import.

        Returns:
            ``{table_name: {"records": int | None, "last_import": datetime | None,
            "file_extension": str | None}}``, one entry per table in the
            schema. ``records`` is ``None`` for tables never imported into.

        Example::

            it.import_file(dataset_id=108953, file=df, table_schema_id=tid).wait()
            it.verify_import(dataset_id=108953)["Reporter"]
            # {'records': 1, 'last_import': datetime(...), 'file_extension': 'csv'}
        """
        from datetime import datetime, timezone

        stats = self._client.get_import_statistics(
            dataset_id=dataset_id, dataflow_id=self._dataflow_id
        )
        schema = self.get_schema(dataset_id=dataset_id)

        def _when(raw: object) -> "datetime | None":
            # The API reports epoch milliseconds.
            if not isinstance(raw, (int, float)):
                return None
            return datetime.fromtimestamp(raw / 1000, tz=timezone.utc)

        result: dict[str, dict[str, object]] = {}
        for table in schema.tables:
            entry = stats.get(table.id) or {}
            result[table.name] = {
                "records": entry.get("numberOfRecordsImported"),
                "last_import": _when(entry.get("lastImportDate")),
                "file_extension": entry.get("fileExtension"),
            }
        return result

    def import_frames(
        self,
        *,
        dataset_id: int,
        frames: dict[str, object],
        replace: bool = False,
        delimiter: str = "|",
        poll_interval: float = 5.0,
        timeout: float | None = None,
    ) -> None:
        """Import multiple tables from a dict of DataFrames (or DuckDB relations).

        Keys in *frames* must match table names in the dataset schema.
        Each table is uploaded and polled to completion sequentially.

        Also accepts DuckDB relations — they are converted to polars DataFrames
        automatically before serialisation.

        Args:
            dataset_id: The dataset to import into.
            frames: Mapping of table name → DataFrame (polars, pandas, modin) or
                DuckDB relation.
            replace: If True, replace all existing rows before importing each table.
            delimiter: CSV column separator (default ``|``).
            poll_interval: Seconds between job status polls.
            timeout: Maximum seconds to wait per table import.

        Raises:
            ValueError: If a key in *frames* does not match any table in the schema.

        Example::

            import polars as pl
            frames = {
                "Table1a": pl.DataFrame({"category": [...], "cyear": [...]}),
                "Table7":  pl.DataFrame({...}),
            }
            flow.import_frames(dataset_id=93953, frames=frames)

            # Also works with a DuckDB relation
            import duckdb
            con = duckdb.connect()
            rel = con.sql("SELECT * FROM 'my_data.parquet'")
            flow.import_frames(dataset_id=93953, frames={"Table1a": rel})
        """
        schema = self.get_schema(dataset_id=dataset_id)
        table_map = {t.name: t.id for t in schema.tables}

        for table_name, frame in frames.items():
            if table_name not in table_map:
                available = list(table_map)
                raise ValueError(
                    f"Table {table_name!r} not found in dataset {dataset_id}. "
                    f"Available: {available}"
                )
            handle = self.import_file(
                dataset_id=dataset_id,
                file=frame,
                table_schema_id=table_map[table_name],
                replace=replace,
                delimiter=delimiter,
            )
            handle.wait(poll_interval=poll_interval, timeout=timeout)

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
        data_provider_codes: str | None = None,
        table_schema_id: str | None = None,
        include_attachments: bool = False,
        version: int | None = None,
    ) -> JobHandle:
        """Export a dataset via the ETL endpoint.

        *version* selects the API version:

        - ``4`` (default for BigData/DLT2 dataflows) — asynchronous, returns a ZIP of CSVs
        - ``3`` (default for Citus dataflows) — asynchronous, returns JSON;
          requires a country code (``dataProviderCodes``), injected automatically
          when the client was created via :meth:`find_reporter`.
        - ``5`` (analytics, opt-in) — asynchronous, returns a ZIP of Parquet files;
          same shape as v4 but smaller/faster to load. Must be requested
          explicitly with ``version=5``; never chosen automatically.

        When *version* is ``None`` (the default), the correct version is chosen
        automatically — between v3 and v4 only. That selection lives in
        :meth:`ReportnetClient.etl_export <reportnet.ReportnetClient.etl_export>`,
        so both client layers behave identically.

        Args:
            data_provider_codes: ISO 3166-1 alpha-2 country code passed as
                ``dataProviderCodes`` to the v3 endpoint (e.g. ``"FR"``).
                Inferred automatically when the client was obtained via
                :meth:`find_reporter`.
            provider_id: Unlike other methods on this class, this is **not**
                auto-filled from the ``provider_id`` this client was scoped
                with (e.g. via :meth:`for_provider` / :meth:`find_reporter`).
                For v4/v5 (BigData), ``dataset_id`` already identifies a
                single provider's dataset, and sending ``providerId`` — even
                the correct one — gets a 403 from the API for reporter-level
                keys. Only pass this if you have confirmed your key/dataflow
                combination needs it.
        """
        # Resolving the version here as well as downstairs looks redundant, but
        # the two scoping decisions below both depend on knowing it. The lookup
        # is cached on the shared client, so this costs no extra request.
        if version is None:
            try:
                version = 4 if self.is_big_dataflow() else 3
            except AuthError:
                # Same failure mode the import path guards against: the backend
                # lookup reads GET /dataflow/v1/{id}, which a reporter-scoped
                # key cannot. Without this the call fails reporting that URL
                # rather than the export endpoint, which is actively misleading.
                version = 4
                logger.warning(
                    "cannot read dataflow %s to detect its backend (not authorised); "
                    "defaulting to etlExport v%d. Pass version= explicitly if this "
                    "dataflow is Citus (v3).",
                    self._dataflow_id, version,
                )
        # v3 (Citus) uses dataProviderCodes (country code) instead of providerId.
        # v4/v5 (BigData) reject providerId outright (403) for reporter-level
        # keys, so — unlike other methods — it is never auto-filled from the
        # stored provider_id here; only an explicit override is forwarded.
        # v3 also accepts dataProviderCodes as a *filter*, but it does not
        # authorise the call on its own — verified live: dataProviderCodes
        # alone is 403, providerId alone succeeds.
        dpc = data_provider_codes or (self._country_code if version == 3 else None)
        resolved_version = version

        def _send(with_pid: int | None) -> JobHandle:
            return self._client.etl_export(
                dataset_id=dataset_id,
                dataflow_id=self._dataflow_id,
                provider_id=with_pid,
                data_provider_codes=dpc,
                table_schema_id=table_schema_id,
                include_attachments=include_attachments,
                version=resolved_version,
            )

        return self._send_with_provider_id(
            _send, override=provider_id, what=f"export of dataset {dataset_id}"
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

    def validate(
        self,
        *,
        dataset_id: int,
        provider_id: int | None = None,
        poll_interval: float = 10.0,
        timeout: float | None = None,
        on_status: Callable[[JobStatus], None] | None = None,
    ) -> ValidationResult:
        """Trigger validation, wait for it to finish, and return structured results.

        Combines :meth:`add_validation_job` + :meth:`~reportnet.JobHandle.wait` +
        the listing endpoint for this dataflow's backend in one call —
        :meth:`list_group_validations_dl` for BigData, :meth:`list_group_validations`
        for Citus. The two are not interchangeable.

        Args:
            dataset_id: Dataset to validate.
            provider_id: Override the stored ``provider_id`` for this call.
            poll_interval: Seconds between job status polls.
            timeout: Maximum seconds to wait for the validation job.
            on_status: Optional callback called with each :class:`~reportnet.JobStatus`
                during polling — useful for progress updates.

        Returns:
            A :class:`~reportnet.ValidationResult` with parsed issues and a
            ``raw`` attribute containing the full API response.

        Raises:
            :class:`~reportnet.DatasetLockedError`: If another job is already running.
            :class:`~reportnet.JobFailedError`: If the validation job fails.
            :class:`~reportnet.JobTimeoutError`: If *timeout* is exceeded.

        Example::

            result = flow.validate(
                dataset_id=93953,
                on_status=lambda s: print(f"  {s}"),
            )
            if result.has_blockers:
                print("Blockers found — cannot submit:")
                print(result.to_frame())
            else:
                print(result.summary())
        """
        handle = self.add_validation_job(dataset_id=dataset_id, provider_id=provider_id)
        handle.wait(poll_interval=poll_interval, timeout=timeout, on_status=on_status)
        raw = self._list_group_validations_for_backend(
            dataset_id=dataset_id, provider_id=provider_id
        )
        return ValidationResult._from_raw(dataset_id, raw)

    def _list_group_validations_for_backend(
        self,
        *,
        dataset_id: int,
        provider_id: int | None,
    ) -> dict[str, object]:
        """Read validation results from the endpoint matching this backend.

        ``listGroupValidationsDL`` is the BigData variant and
        ``listGroupValidations`` the Citus one; they are not interchangeable.
        :meth:`validate` used to call the DL endpoint unconditionally, which
        is wrong for every Citus dataflow.

        If the backend cannot be determined (a reporter-scoped key may not be
        able to read the dataflow), the DL endpoint is tried first and the
        Citus one used as a fallback, so neither backend is left unserved.
        """
        try:
            is_big = self.is_big_dataflow()
        except AuthError:
            logger.warning(
                "cannot read dataflow %s to detect its backend (not authorised); "
                "trying listGroupValidationsDL then falling back to listGroupValidations",
                self._dataflow_id,
            )
            try:
                return self.list_group_validations_dl(
                    dataset_id=dataset_id, provider_id=provider_id
                )
            except ReportnetError:
                return self.list_group_validations(
                    dataset_id=dataset_id, provider_id=provider_id
                )
        if is_big:
            return self.list_group_validations_dl(
                dataset_id=dataset_id, provider_id=provider_id
            )
        return self.list_group_validations(dataset_id=dataset_id, provider_id=provider_id)

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

    def get_codelists(
        self,
        *,
        dataset_id: int,
        ref_dataset_id: int,
        poll_interval: float = 5.0,
        timeout: float | None = None,
        strict: bool = False,
    ) -> dict[str, list[str]]:
        """Return valid values for all LINK fields in *dataset_id*.

        Exports the reference dataset (*ref_dataset_id*), then maps each LINK
        field in the reporting dataset to the sorted list of valid values from
        the column it references.

        A dataflow can have several reference datasets, and a LINK field is
        only resolvable from the one that actually holds its lookup table. Any
        field that could not be resolved is logged and warned about — a
        partially-resolved mapping looks exactly like a complete one, and
        silently produces templates that enforce nothing. Use *strict* to turn
        that into an error, or :meth:`get_template`, which picks the right
        reference dataset for you.

        Args:
            dataset_id: The reporting dataset whose LINK fields to resolve.
            ref_dataset_id: The reference dataset that holds the codelist data.
            poll_interval: Seconds between export polling calls.
            timeout: Maximum seconds to wait for the export job.
            strict: Raise :class:`~reportnet.CodelistResolutionError` instead of
                warning when some LINK fields cannot be resolved.

        Returns:
            A dict mapping field name → list of valid string values.

        Raises:
            CodelistResolutionError: If *strict* and any field is unresolved.

        Example::

            codelists = df.get_codelists(dataset_id=93953, ref_dataset_id=12345)
            # {"category": ["Total excluding LULUCF", "Total including LULUCF"],
            #  "scenario": ["WAM", "WEM", "WOM"], "ry": ["0", "1"]}

            # Use when building a template DataFrame — LINK columns become Enum
            template = (
                df.get_schema(dataset_id=93953).table("Table1a").to_frame(codelists=codelists)
            )
        """
        resolution = self._resolve_codelists(
            dataset_id=dataset_id,
            ref_dataset_id=ref_dataset_id,
            poll_interval=poll_interval,
            timeout=timeout,
        )
        self._report_codelist_coverage(resolution, ref_dataset_id, strict=strict)
        return resolution.values

    def _resolve_codelists(
        self,
        *,
        dataset_id: int,
        ref_dataset_id: int,
        poll_interval: float,
        timeout: float | None,
    ) -> "CodelistResolution":
        from ._util import build_codelists

        reporting_schema = self.get_schema(dataset_id=dataset_id)
        ref_schema = self.get_schema(dataset_id=ref_dataset_id)
        logger.info("exporting reference dataset %d to resolve codelists", ref_dataset_id)
        ref_frames = self.etl_export(dataset_id=ref_dataset_id).to_frames(
            poll_interval=poll_interval, timeout=timeout
        )
        return build_codelists(reporting_schema, ref_schema, ref_frames)

    @staticmethod
    def _report_codelist_coverage(
        resolution: "CodelistResolution",
        ref_dataset_id: int,
        *,
        strict: bool,
    ) -> None:
        """Log coverage, and warn or raise when it is incomplete."""
        logger.info("codelists from reference dataset %d: %s", ref_dataset_id, resolution.summary())
        if resolution.is_complete:
            return
        detail = (
            f"Reference dataset {ref_dataset_id} does not contain lookup values for "
            f"these fields; those columns will accept any string. "
            f"Another reference dataset in this dataflow may hold them — "
            f"get_template() selects one automatically."
        )
        if strict:
            raise CodelistResolutionError(list(resolution.unresolved), detail)
        warnings.warn(
            f"{resolution.summary()}. {detail}",
            UserWarning,
            stacklevel=3,
        )
        logger.warning("unresolved LINK/CODELIST fields: %s", sorted(resolution.unresolved))

    def _best_reference_dataset(
        self, reporting_schema: DatasetSchema, refs: list[ReferenceDataset]
    ) -> ReferenceDataset | None:
        """Pick the reference dataset whose schema covers the most LINK fields.

        Compares schema IDs only — no data export — so this costs one cheap
        GET per reference dataset rather than one export job each. Picking
        ``refs[0]`` blindly is wrong on real dataflows: on dataflow 2003 the
        codelists live in the *fourth* reference dataset.
        """
        from ._util import reference_coverage

        best: ReferenceDataset | None = None
        best_score = 0
        for ref in refs:
            try:
                score = reference_coverage(reporting_schema, self.get_schema(dataset_id=ref.id))
            except ReportnetError as exc:
                logger.warning("could not read schema of reference dataset %d: %s", ref.id, exc)
                continue
            logger.debug(
                "reference dataset %d (%s) covers %d LINK field(s)", ref.id, ref.name, score
            )
            if score > best_score:
                best, best_score = ref, score
        if best is None:
            logger.warning(
                "none of the %d reference dataset(s) match this dataset's LINK fields", len(refs)
            )
        else:
            logger.info(
                "selected reference dataset %d (%s), covering %d LINK field(s)",
                best.id, best.name, best_score,
            )
        return best

    def get_template(
        self,
        *,
        dataset_id: int,
        ref_dataset_id: int | None = None,
        poll_interval: float = 5.0,
        timeout: float | None = None,
        strict: bool = False,
    ) -> "dict[str, object]":
        """Return empty, fully-typed DataFrames for every table in *dataset_id*.

        Combines schema introspection and codelist resolution in one call:

        1. Fetches the dataset schema (field names and types).
        2. Locates the reference dataset — uses *ref_dataset_id* if given,
           otherwise picks the one whose schema actually covers this dataset's
           LINK fields (comparing schema IDs, which costs one cheap request per
           reference dataset and no export jobs).  If nothing covers them, LINK /
           CODELIST columns are left as plain strings **and a warning is issued**.
        3. Exports the reference data and resolves codelist values.
        4. Returns one empty DataFrame per table, with:

           - Numeric / date / boolean columns cast to their schema types.
           - LINK and CODELIST columns cast to ``pl.Enum`` (polars) or
             ``CategoricalDtype`` (pandas) so invalid values are rejected
             at assignment time rather than silently accepted.

        Requires ``pip install reportnet-client[dataframe]``.

        Args:
            dataset_id: The reporting dataset to build templates for.
            ref_dataset_id: ID of the reference dataset to pull codelists from.
                Auto-detected from the dataflow when omitted.
            poll_interval: Seconds between polls while exporting the reference data.
            timeout: Maximum seconds to wait for the reference export job.
            strict: Raise :class:`~reportnet.CodelistResolutionError` instead of
                warning when LINK/CODELIST columns cannot be constrained. Use
                this when a template that silently accepts anything would be
                worse than no template at all.

        Returns:
            A ``dict`` mapping table name → empty typed DataFrame.

        Raises:
            CodelistResolutionError: If *strict* and any LINK field is unresolved.

        Example::

            templates = flow.get_template(dataset_id=93953)
            # {"Table1a": <empty polars.DataFrame with Enum columns>,
            #  "Table7":  <empty polars.DataFrame>}

            # Fill a table and upload
            import polars as pl
            df = pl.concat([templates["Table1a"], pl.DataFrame({
                "category": ["Total including LULUCF"],
                "cyear":    [2024],
                "cvalue":   [1234.5],
            }).cast({col: templates["Table1a"].schema[col]
                     for col in ["category"]})])
            flow.import_file(dataset_id=93953, file=df)
        """
        from ._util import linked_field_names

        schema = self.get_schema(dataset_id=dataset_id)
        linked = linked_field_names(schema)

        _ref_id = ref_dataset_id
        if _ref_id is None and linked:
            # Don't guess refs[0] — pick the reference dataset that actually
            # holds these LINK fields' lookup tables (cheap, schema-only).
            best = self._best_reference_dataset(schema, self.get_reference_datasets())
            _ref_id = best.id if best is not None else None

        codelists: dict[str, list[str]] | None = None
        if _ref_id is not None:
            try:
                resolution = self._resolve_codelists(
                    dataset_id=dataset_id,
                    ref_dataset_id=_ref_id,
                    poll_interval=poll_interval,
                    timeout=timeout,
                )
                codelists = resolution.values
                self._report_codelist_coverage(resolution, _ref_id, strict=strict)
            except CodelistResolutionError:
                raise
            except ReportnetError as exc:
                # Codelist retrieval can fail for several reasons: the reporter
                # key may be forbidden from exporting the reference dataset
                # (403), the export job may fail server-side, or the job may
                # time out.  Fall back to plain-string LINK columns rather than
                # failing — numeric, date, and boolean columns are still typed.
                # This weakens the result, so it is never silent.
                if strict:
                    raise CodelistResolutionError(
                        linked, f"Reference export failed: {exc}"
                    ) from exc
                warnings.warn(
                    f"Could not resolve codelists from reference dataset {_ref_id} ({exc}); "
                    f"LINK/CODELIST columns will accept any string. "
                    f"Affected fields: {sorted(linked)}",
                    UserWarning,
                    stacklevel=2,
                )
                logger.warning("codelist resolution failed for dataset %d: %s", dataset_id, exc)
        elif linked:
            message = (
                f"This dataset has {len(linked)} LINK/CODELIST field(s) but no reference "
                f"dataset provides their values; those columns will accept any string. "
                f"Affected fields: {sorted(linked)}"
            )
            if strict:
                raise CodelistResolutionError(linked, message)
            warnings.warn(message, UserWarning, stacklevel=2)

        return schema.to_frames(codelists=codelists)

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

    # ── Visualisation ─────────────────────────────────────────────────────────

    def to_mermaid(self, *, include_test: bool = False) -> str:
        """Return a Mermaid diagram string describing this dataflow's structure.

        Renders natively in marimo without any CLI tools::

            mo.mermaid(flow.to_mermaid())

        One compact node per reporter country, coloured by their worst
        submission status across all tables (green = all FINAL, yellow =
        correction requested, grey = pending).  Reference and test datasets
        are shown as separate nodes connected to the dataflow.

        Costs a single API request — the rendering itself lives in
        :func:`reportnet.viz.dataflow_to_mermaid`, which takes already-fetched
        models if you'd rather supply your own.

        Args:
            include_test: When True, also show test datasets.

        Returns:
            A Mermaid ``graph LR`` diagram string.
        """
        from .viz import dataflow_to_mermaid

        contents = self.get_dataflow_contents()
        return dataflow_to_mermaid(
            contents.info,
            reporting_datasets=contents.reporting_datasets,
            reference_datasets=contents.reference_datasets,
            test_datasets=contents.test_datasets if include_test else (),
        )
