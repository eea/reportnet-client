"""Pure export inspection and conservative row comparison (no network calls)."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .models import DatasetSchema, ExportVerification, FieldSchema, FieldType, TableSchema


def verify_export(
    frames: dict[str, Any], schema: DatasetSchema, *, dataset_id: int,
    table_schema_id: str | None = None,
) -> ExportVerification:
    """Check exact table names and schema fields, allowing RN3 metadata columns.

    A zero-byte CSV lacks its columns and therefore fails structural verification.
    Empty tables with schema headers pass, with zero rows explicitly reported.
    """
    tables = [t for t in schema.tables if table_schema_id is None or t.id == table_schema_id]
    if table_schema_id is not None and not tables:
        raise ValueError(f"Table schema {table_schema_id!r} is not in dataset {dataset_id}")
    expected = {t.name for t in tables}
    actual = set(frames)
    missing_columns = {}
    unexpected_columns = {}
    for table in tables:
        if table.name not in frames:
            continue
        columns = set(frames[table.name].columns)
        missing = set(table.column_names()) - columns
        unexpected = columns - set(table.column_names()) - {"record_id", "data_provider_code"}
        if missing:
            missing_columns[table.name] = tuple(sorted(missing))
        if unexpected:
            unexpected_columns[table.name] = tuple(sorted(unexpected))
    return ExportVerification(
        dataset_id, tuple(sorted(expected)), tuple(sorted(actual)),
        tuple(sorted(expected - actual)), tuple(sorted(actual - expected)),
        missing_columns, unexpected_columns,
        {name: int(frame.shape[0]) for name, frame in frames.items()},
    )


def frame_rows(frame: object) -> list[dict[str, Any]]:
    import narwhals as nw

    return list(nw.from_native(frame, eager_only=True).iter_rows(named=True))  # type: ignore[call-overload]


def _value(value: Any, field: FieldSchema) -> Any:
    # CSV cannot distinguish an empty field from null. This policy is explicit
    # in the workflow API; no whitespace trimming or fuzzy numeric tolerance.
    if value is None or isinstance(value, (str, bytes)) and not value:
        return None
    kind = field.type
    if kind in {FieldType.NUMBER_INTEGER, FieldType.NUMBER_DECIMAL,
                FieldType.COORDINATE_LAT, FieldType.COORDINATE_LONG}:
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError(f"Non-finite value in {field.name}")
        if kind == FieldType.NUMBER_INTEGER and number != number.to_integral_value():
            raise ValueError(f"Non-integer value in {field.name}")
        return number
    if kind == FieldType.BOOLEAN:
        text = str(value).lower()
        if text not in {"true", "false", "1", "0"}:
            raise ValueError(f"Invalid boolean in {field.name}")
        return text in {"true", "1"}
    if kind in {FieldType.DATE, FieldType.DATETIME}:
        text = value.isoformat() if isinstance(value, (date, datetime)) else str(value)
        return (date.fromisoformat(text) if kind == FieldType.DATE
                else datetime.fromisoformat(text.replace("Z", "+00:00")))
    if kind.value in {"POINT", "LINESTRING", "POLYGON", "MULTIPOINT",
                      "MULTILINESTRING", "MULTIPOLYGON", "GEOMETRYCOLLECTION"}:
        try:
            from shapely import wkb, wkt  # type: ignore[import-untyped]
            from shapely.geometry import shape  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError("Geometry readback requires reportnet-client[spatial]") from None
        if isinstance(value, bytes):
            geometry = wkb.loads(value)
        elif isinstance(value, str) and value.lstrip().startswith("{"):
            obj = json.loads(value)
            geometry = shape(obj.get("geometry") or obj)
        elif hasattr(value, "geom_type"):
            geometry = value
        else:
            geometry = wkt.loads(str(value))
        # Exact coordinates/order, no topology tolerance; normalize transport
        # encoding only. The caller must prepare data in the dataset's CRS.
        return wkb.dumps(geometry, big_endian=True, include_srid=False)
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def row_counts(frame: object, table: TableSchema) -> Counter[tuple[Any, ...]]:
    """Schema-ordered values, ignoring server IDs; retain duplicate rows."""
    return Counter(tuple(_value(row.get(f.name), f) for f in table.fields)
                   for row in frame_rows(frame))
