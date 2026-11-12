"""Design a dataset schema safely: name-based helpers, guards and read-back.

:class:`SchemaDesigner` composes public :class:`~reportnet.ReportnetClient`
methods and holds no endpoint knowledge (the same rule as
:mod:`reportnet.workflows`). What it adds is the care the raw API does not take
(all verified on sandbox dataflow 11468, 2026-11-12):

* **Login token only.** API keys get 403 on every schema write; refused here
  before any request.
* **Design datasets only**, and only while the schema has no data collection
  or reporting datasets, unless ``allow_after_data_collection=True``. Changes
  after that point reach reporters, and that behaviour has not been tested.
* **Tables with data are locked.** The web app refuses to change them; the API
  does not. Refused here unless ``force=True``.
* **No duplicate names.** The API accepts two tables called "Sites". Compared
  case-insensitively, because QC rules address tables in lower case.
* **Whole-field updates.** A partial field update answered 500 and still saved.
* **Read back after every write.** Each method returns the object as read
  back from Reportnet and raises :class:`~reportnet.SchemaReadbackError` if it
  differs from what was asked.

Example::

    client = ReportnetClient.from_tokens(access_token=..., refresh_token=...,
                                         sandbox=True)
    flow = client.for_dataflow(11468)
    ds = flow.create_design_dataset("Sites and measurements")
    designer = flow.design(ds.id)

    sites = designer.add_table("Sites", mandatory=True)
    code = designer.add_field(sites, "SiteCode", "TEXT", pk=True, required=True)
    designer.add_field(sites, "Status", "CODELIST", codelist=["open", "closed"])
    designer.update_field(code, description="Site code")
    designer.move_field(code, position=0)
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Mapping, Sequence, Union

from ._log import get_logger
from .exceptions import (
    APIError,
    DuplicateNameError,
    SchemaDesignError,
    SchemaDesignNotPermittedError,
    SchemaReadbackError,
    TableHasDataError,
)
from .models import DatasetSchema, FieldSchema, FieldType, TableSchema

if TYPE_CHECKING:
    from .dataflow import DataflowClient

logger = get_logger(__name__)

TableRef = Union[TableSchema, str]
"""A table, its id, or its name."""
FieldRef = Union[FieldSchema, str]
"""A field or its id."""

# Model attribute compared on read-back, per keyword accepted by the designer.
_FIELD_ATTR = {
    "name": "name", "description": "description", "type": "type",
    "required": "required", "pk": "pk", "read_only": "read_only",
    "codelist_items": "codelist_items", "max_size": "max_size",
}
_TABLE_ATTR = {
    "name": "name", "description": "description", "not_empty": "not_empty",
    "read_only": "read_only", "to_prefill": "to_prefill",
    "fixed_number": "fixed_number", "data_manually_editable": "data_manually_editable",
}


def _normalise(key: str, value: Any) -> Any:
    if key == "type":
        return FieldType(value).value
    if key == "codelist_items":
        return tuple(value)
    if key == "max_size":
        return None if value is None else int(value)
    if key == "description":
        return value or ""
    return value


def _differences(obj: object, attrs: Mapping[str, str],
                 wanted: Mapping[str, Any]) -> tuple[dict[str, object], dict[str, object]]:
    expected: dict[str, object] = {}
    actual: dict[str, object] = {}
    for key, value in wanted.items():
        if key not in attrs:
            continue
        have = _normalise(key, getattr(obj, attrs[key]))
        want = _normalise(key, value)
        if have != want:
            expected[key], actual[key] = want, have
    return expected, actual


class SchemaDesigner:
    """Change one design dataset's schema. Obtain via :meth:`DataflowClient.design`."""

    def __init__(
        self,
        flow: "DataflowClient",
        dataset_id: int,
        *,
        allow_after_data_collection: bool = False,
    ) -> None:
        self._flow = flow
        self._client = flow._client
        self.dataset_id = dataset_id
        if self._client.auth_kind != "bearer":
            raise SchemaDesignNotPermittedError("Schema design")

        contents = flow.get_dataflow_contents()
        design = {d.id: d for d in contents.design_datasets}
        if dataset_id not in design:
            raise SchemaDesignError(
                f"Dataset {dataset_id} is not a design dataset of dataflow "
                f"{flow._dataflow_id}; schemas are changed on design datasets only. "
                f"Design datasets: {sorted((d.id, d.name) for d in design.values())}"
            )
        self.schema_id = design[dataset_id].schema_id
        # Only copies of *this* schema matter: a design dataset added after the
        # dataflow's data collections were created has none, and is safe.
        copies = [d.name for d in contents.data_collections if d.schema_id == self.schema_id]
        copies += [d.name for d in contents.reporting_datasets if d.schema_id == self.schema_id]
        if copies and not allow_after_data_collection:
            raise SchemaDesignError(
                f"Design dataset {dataset_id} already has {len(copies)} data collection or "
                "reporting dataset(s), so a schema change would reach reporters. This has "
                "not been tested. Pass allow_after_data_collection=True to flow.design() "
                "if you are sure."
            )
        self._big_data = contents.info.big_data

    # ── reading ───────────────────────────────────────────────────────────────

    def schema(self) -> DatasetSchema:
        """The schema as Reportnet holds it now (always a fresh read)."""
        return self._client.get_schema(dataset_id=self.dataset_id)

    def table(self, ref: TableRef) -> TableSchema:
        """Find a table by object, id or name in a fresh read."""
        return self._find_table(self.schema(), ref)

    def field(self, ref: FieldRef) -> FieldSchema:
        """Find a field by object or id in a fresh read."""
        return self._find_field(self.schema(), ref)[1]

    def record_count(self, table: TableRef) -> int:
        """How many records the table holds now."""
        t = self.table(table)
        return self._count(t)

    # ── dataset ───────────────────────────────────────────────────────────────

    def rename(self, name: str) -> DatasetSchema:
        """Rename the design dataset (and its schema)."""
        self._client.update_dataset_name(dataset_id=self.dataset_id, name=name)
        after = self.schema()
        if after.name != name:
            raise SchemaReadbackError("rename", {"name": name}, {"name": after.name})
        return after

    def set_description(self, description: str) -> DatasetSchema:
        """Set the dataset's description."""
        self._client.update_dataset_schema(dataset_id=self.dataset_id,
                                           description=description)
        after = self.schema()
        if after.description != description:
            raise SchemaReadbackError("set_description", {"description": description},
                                      {"description": after.description})
        return after

    # ── tables ────────────────────────────────────────────────────────────────

    def add_table(self, name: str, *, mandatory: bool = False,
                  description: str | None = None, **props: Any) -> TableSchema:
        """Add a table; returns it as read back.

        *mandatory* is the web app's "Mandatory table" (``notEmpty``). Other
        keywords: ``read_only``, ``to_prefill``, ``fixed_number``,
        ``data_manually_editable``.
        """
        self._check_new_table_name(self.schema(), name)
        created = self._client.create_table_schema(
            dataset_id=self.dataset_id, name=name, not_empty=mandatory)
        extra = dict(props)
        if description is not None:
            extra["description"] = description
        if extra:
            self._client.update_table_schema(
                dataset_id=self.dataset_id, table_schema_id=created.id, **extra)
        logger.info("added table %r (%s) to dataset %s", name, created.id, self.dataset_id)
        return self._readback_table("add_table", created.id,
                                    {"name": name, "not_empty": mandatory, **extra})

    def update_table(self, table: TableRef, *, force: bool = False,
                     **props: Any) -> TableSchema:
        """Change table properties (``name``, ``description``, ``not_empty``, …)."""
        schema = self.schema()
        t = self._find_table(schema, table)
        self._guard_data(t, force)
        if "name" in props and props["name"].casefold() != t.name.casefold():
            self._check_new_table_name(schema, props["name"])
        self._client.update_table_schema(
            dataset_id=self.dataset_id, table_schema_id=t.id, **props)
        return self._readback_table("update_table", t.id, props)

    def move_table(self, table: TableRef, position: int) -> DatasetSchema:
        """Move a table to *position* (0-based)."""
        t = self.table(table)
        self._client.order_table_schema(
            dataset_id=self.dataset_id, table_schema_id=t.id, position=position)
        after = self.schema()
        ids = [x.id for x in after.tables]
        if ids.index(t.id) != position:
            raise SchemaReadbackError("move_table", {"position": position},
                                      {"position": ids.index(t.id)})
        return after

    def delete_table(self, table: TableRef, *, force: bool = False) -> None:
        """Delete a table and all its fields. **No undo.**"""
        t = self.table(table)
        self._guard_data(t, force)
        self._client.delete_table_schema(dataset_id=self.dataset_id, table_schema_id=t.id)
        if any(x.id == t.id for x in self.schema().tables):
            raise SchemaReadbackError("delete_table", {"present": False}, {"present": True})
        logger.info("deleted table %r (%s) from dataset %s", t.name, t.id, self.dataset_id)

    def export_table_definition(self, table: TableRef) -> str:
        """The table's field definitions as CSV text (the web app's export)."""
        t = self.table(table)
        return self._client.export_table_definition(
            dataset_schema_id=self.schema_id, dataset_id=self.dataset_id,
            table_schema_id=t.id)

    # ── fields ────────────────────────────────────────────────────────────────

    def add_field(
        self,
        table: TableRef,
        name: str,
        type: FieldType | str,
        *,
        description: str = "",
        required: bool = False,
        pk: bool = False,
        read_only: bool = False,
        codelist: Sequence[str] = (),
        link_to: FieldSchema | Mapping[str, str] | None = None,
        max_size: int | None = None,
        force: bool = False,
    ) -> FieldSchema:
        """Add a field to *table*; returns it as read back.

        Args:
            codelist: Allowed values for a CODELIST or MULTISELECT_CODELIST field.
            link_to: For a LINK field, the primary-key field it points to. A
                :class:`FieldSchema` is taken to be in **this** dataset; for
                another design dataset pass
                ``{"idDatasetSchema": <schema id>, "idPk": <field id>}``.
        """
        schema = self.schema()
        t = self._find_table(schema, table)
        self._guard_data(t, force)
        if any(f.name.casefold() == name.casefold() for f in t.fields):
            raise DuplicateNameError(f"Table {t.name!r} already has a field named {name!r}.")
        ref: Mapping[str, str] | None
        if isinstance(link_to, FieldSchema):
            ref = {"idDatasetSchema": self.schema_id, "idPk": link_to.id}
        else:
            ref = link_to
        field_id = self._client.create_field_schema(
            dataset_id=self.dataset_id, record_id=t.record_id, name=name, type=type,
            description=description, required=required, pk=pk, read_only=read_only,
            codelist_items=codelist, referenced_field=ref, max_size=max_size)
        logger.info("added field %r (%s) to table %r", name, field_id, t.name)
        wanted: dict[str, Any] = {"name": name, "type": type, "description": description,
                                  "required": required, "pk": pk, "read_only": read_only,
                                  "codelist_items": codelist}
        after = self._readback_field("add_field", field_id, wanted)
        if ref and after.referenced_pk_id != ref.get("idPk"):
            raise SchemaReadbackError("add_field", {"link_to": ref.get("idPk")},
                                      {"link_to": after.referenced_pk_id})
        return after

    def update_field(self, field: FieldRef, *, force: bool = False,
                     **changes: Any) -> FieldSchema:
        """Change field properties; sends the whole field (read-modify-write).

        The field is re-read first, so a stale :class:`FieldSchema` you pass in
        never overwrites a newer change. Keywords are those of
        :meth:`FieldSchema.to_update_payload`.
        """
        schema = self.schema()
        t, current = self._find_field(schema, field)
        self._guard_data(t, force)
        if "name" in changes and changes["name"].casefold() != current.name.casefold():
            if any(f.name.casefold() == changes["name"].casefold() for f in t.fields):
                raise DuplicateNameError(
                    f"Table {t.name!r} already has a field named {changes['name']!r}.")
        self._client.update_field_schema(
            dataset_id=self.dataset_id, payload=current.to_update_payload(**changes))
        return self._readback_field("update_field", current.id, changes)

    def move_field(self, field: FieldRef, position: int, *, force: bool = False) -> TableSchema:
        """Move a field to *position* within its table (0-based).

        Field order is the column order Reportnet expects in import files, so
        this is guarded like any other change to a table with data.
        """
        t, f = self._find_field(self.schema(), field)
        self._guard_data(t, force)
        self._client.order_field_schema(
            dataset_id=self.dataset_id, field_schema_id=f.id, position=position)
        after = self.table(t.id)
        ids = [x.id for x in after.fields]
        if ids.index(f.id) != position:
            raise SchemaReadbackError("move_field", {"position": position},
                                      {"position": ids.index(f.id)})
        return after

    def delete_field(self, field: FieldRef, *, force: bool = False) -> None:
        """Delete a field. **No undo.**"""
        t, f = self._find_field(self.schema(), field)
        self._guard_data(t, force)
        if f.pk_referenced:
            warnings.warn(f"Field {f.name!r} is a primary key that a LINK field uses.",
                          stacklevel=2)
            logger.warning("deleting %r, a primary key that a LINK field uses", f.name)
        self._client.delete_field_schema(dataset_id=self.dataset_id, field_schema_id=f.id)
        if any(x.id == f.id for x in self.table(t.id).fields):
            raise SchemaReadbackError("delete_field", {"present": False}, {"present": True})
        logger.info("deleted field %r (%s) from table %r", f.name, f.id, t.name)

    # ── internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _find_table(schema: DatasetSchema, ref: TableRef) -> TableSchema:
        key = ref.id if isinstance(ref, TableSchema) else ref
        for t in schema.tables:
            if t.id == key:
                return t
        matches = [t for t in schema.tables if t.name == key]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise DuplicateNameError(
                f"{len(matches)} tables are named {key!r}; pass the table id instead.")
        raise KeyError(f"No table {key!r}; available: {[t.name for t in schema.tables]}")

    @staticmethod
    def _find_field(schema: DatasetSchema, ref: FieldRef) -> tuple[TableSchema, FieldSchema]:
        key = ref.id if isinstance(ref, FieldSchema) else ref
        for t in schema.tables:
            for f in t.fields:
                if f.id == key:
                    return t, f
        raise KeyError(f"No field with id {key!r} in dataset; pass a FieldSchema or field id.")

    @staticmethod
    def _check_new_table_name(schema: DatasetSchema, name: str) -> None:
        if any(t.name.casefold() == name.casefold() for t in schema.tables):
            raise DuplicateNameError(f"The dataset already has a table named {name!r}.")

    def _count(self, t: TableSchema) -> int:
        if self._big_data:
            return self._client.count_table_records(
                dataset_id=self.dataset_id, table_schema_id=t.id)
        # Citus: no record-count route has been verified, so use the import
        # statistics. They count the last import, not later manual edits.
        stats = self._client.get_import_statistics(
            dataset_id=self.dataset_id, dataflow_id=self._flow._dataflow_id)
        entry = stats.get(t.id) or {}
        message = (f"Table {t.name!r}: record count taken from the last import "
                   "(manual edits in the web app are not counted).")
        warnings.warn(message, stacklevel=3)
        logger.warning(message)
        return int(entry.get("numberOfRecordsImported") or 0)

    def _guard_data(self, t: TableSchema, force: bool) -> None:
        if force:
            logger.warning("force=True: skipping the data check on table %r", t.name)
            return
        try:
            records = self._count(t)
        except APIError as exc:
            raise SchemaDesignError(
                f"Could not check whether table {t.name!r} holds data ({exc}). "
                "Pass force=True to change it without the check."
            ) from exc
        if records:
            raise TableHasDataError(t.name, records)

    def _readback_table(self, operation: str, table_id: str,
                        wanted: Mapping[str, Any]) -> TableSchema:
        after = self.table(table_id)
        expected, actual = _differences(after, _TABLE_ATTR, wanted)
        if expected:
            raise SchemaReadbackError(operation, expected, actual)
        return after

    def _readback_field(self, operation: str, field_id: str,
                        wanted: Mapping[str, Any]) -> FieldSchema:
        try:
            after = self.field(field_id)
        except KeyError:
            raise SchemaReadbackError(operation, {"field": field_id}, {"field": None}) from None
        expected, actual = _differences(after, _FIELD_ATTR, wanted)
        if expected:
            raise SchemaReadbackError(operation, expected, actual)
        return after
