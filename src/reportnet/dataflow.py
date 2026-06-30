from __future__ import annotations

from pathlib import Path
from typing import IO, TYPE_CHECKING, Callable, Literal, Union

from .models import (
    DataflowInfo,
    DatasetSchema,
    JobHandle,
    JobStatus,
    ReferenceDataset,
    Reporter,
    ReportingDataset,
    TestDataset,
    ValidationResult,
)

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
        return self.for_provider(matches[0].provider_id)

    # ── Dataflow metadata ─────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Return True if the API key is valid and the API is reachable."""
        return self._client.ping(dataflow_id=self._dataflow_id)

    def get_dataflow(self) -> DataflowInfo:
        """Return name, type and status of this dataflow."""
        return self._client.get_dataflow(dataflow_id=self._dataflow_id)

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
            ie = flow.for_provider(42)
            datasets = ie.get_reporting_datasets()
            # [ReportingDataset(id=93953, table_name='Table1a', ...),
            #  ReportingDataset(id=93954, table_name='Table7', ...)]

            # Unscoped — returns every reporter's datasets
            all_ds = flow.get_reporting_datasets()
        """
        all_ds = self._client.get_reporting_datasets(dataflow_id=self._dataflow_id)
        if self._provider_id is not None:
            return [ds for ds in all_ds if ds.provider_id == self._provider_id]
        return all_ds

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
        return self._client.get_reference_datasets(dataflow_id=self._dataflow_id)

    def get_test_datasets(self) -> list[TestDataset]:
        """Return all test datasets for this dataflow.

        Test datasets mirror the reporting schema and can be used by custodians
        to verify validation rules before the reporting period opens.

        Example::

            test_ds = flow.get_test_datasets()
            # [TestDataset(id=93953, name='Test Dataset - Table1a', ...)]
            flow.import_file(dataset_id=test_ds[0].id, file="sample.csv")
        """
        return self._client.get_test_datasets(dataflow_id=self._dataflow_id)

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
        :meth:`list_group_validations_dl` in one call.

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
        raw = self.list_group_validations_dl(dataset_id=dataset_id, provider_id=provider_id)
        return ValidationResult._from_raw(dataset_id, raw)

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
    ) -> dict[str, list[str]]:
        """Return valid values for all LINK fields in *dataset_id*.

        Exports the reference dataset (*ref_dataset_id*), then maps each LINK
        field in the reporting dataset to the sorted list of valid values from
        the column it references.

        Args:
            dataset_id: The reporting dataset whose LINK fields to resolve.
            ref_dataset_id: The reference dataset that holds the codelist data.
            poll_interval: Seconds between export polling calls.
            timeout: Maximum seconds to wait for the export job.

        Returns:
            A dict mapping field name → list of valid string values.

        Example::

            codelists = df.get_codelists(dataset_id=93953, ref_dataset_id=12345)
            # {"category": ["Total excluding LULUCF", "Total including LULUCF"],
            #  "scenario": ["WAM", "WEM", "WOM"], "ry": ["0", "1"]}

            # Use when building a template DataFrame — LINK columns become Enum
            template = (
                df.get_schema(dataset_id=93953).table("Table1a").to_frame(codelists=codelists)
            )
        """
        from ._util import build_codelists

        reporting_schema = self.get_schema(dataset_id=dataset_id)
        ref_schema = self.get_schema(dataset_id=ref_dataset_id)
        ref_frames = self.etl_export(dataset_id=ref_dataset_id).to_frames(
            poll_interval=poll_interval, timeout=timeout
        )
        return build_codelists(reporting_schema, ref_schema, ref_frames)

    def get_template(
        self,
        *,
        dataset_id: int,
        ref_dataset_id: int | None = None,
        poll_interval: float = 5.0,
        timeout: float | None = None,
    ) -> "dict[str, object]":
        """Return empty, fully-typed DataFrames for every table in *dataset_id*.

        Combines schema introspection and codelist resolution in one call:

        1. Fetches the dataset schema (field names and types).
        2. Locates the reference dataset — uses *ref_dataset_id* if given,
           otherwise picks the first reference dataset for this dataflow
           automatically.  If the dataflow has no reference datasets, LINK /
           CODELIST columns are left as plain strings.
        3. Exports the reference data and resolves codelist values.
        4. Returns one empty DataFrame per table, with:

           - Numeric / date / boolean columns cast to their schema types.
           - LINK and CODELIST columns cast to ``pl.Enum`` (polars) or
             ``CategoricalDtype`` (pandas) so invalid values are rejected
             at assignment time rather than silently accepted.

        Requires ``pip install reportnet[dataframe]``.

        Args:
            dataset_id: The reporting dataset to build templates for.
            ref_dataset_id: ID of the reference dataset to pull codelists from.
                Auto-detected from the dataflow when omitted.
            poll_interval: Seconds between polls while exporting the reference data.
            timeout: Maximum seconds to wait for the reference export job.

        Returns:
            A ``dict`` mapping table name → empty typed DataFrame.

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
        schema = self.get_schema(dataset_id=dataset_id)

        _ref_id = ref_dataset_id
        if _ref_id is None:
            refs = self.get_reference_datasets()
            _ref_id = refs[0].id if refs else None

        codelists: dict[str, list[str]] | None = None
        if _ref_id is not None:
            codelists = self.get_codelists(
                dataset_id=dataset_id,
                ref_dataset_id=_ref_id,
                poll_interval=poll_interval,
                timeout=timeout,
            )

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
