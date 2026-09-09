from __future__ import annotations

import io
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, TypeAlias, Union

from ._log import get_logger

if TYPE_CHECKING:
    import pandas  # type: ignore[import-untyped]
    import polars

    NativeFrame: TypeAlias = Union[polars.DataFrame, pandas.DataFrame]

logger = get_logger(__name__)


def to_file_tuple(
    file: Union[str, Path, bytes, IO[bytes], object],
    filename: str | None,
    *,
    delimiter: str = "|",
) -> tuple[str, bytes]:
    """Return (filename, bytes) for any accepted file input.

    When *file* is a DataFrame, it is serialized to CSV using *delimiter* so
    the uploaded bytes match the delimiter sent to the API.
    """
    if isinstance(file, (str, Path)):
        path = Path(file)
        return filename or path.name, path.read_bytes()

    if isinstance(file, bytes):
        return filename or "upload.csv", file

    if hasattr(file, "read"):
        content: bytes = file.read()
        name: str = getattr(file, "name", None) or "upload.csv"
        return filename or name, content

    # DuckDB relation — convert to polars before narwhals sees it
    if type(file).__name__ == "DuckDBPyRelation":
        return to_file_tuple(getattr(file, "pl")(), filename, delimiter=delimiter)

    # GeoDataFrame — geometry column serialised as WKT by geopandas .to_csv()
    if type(file).__name__ == "GeoDataFrame":
        buf = io.BytesIO()
        getattr(file, "to_csv")(buf, index=False, sep=delimiter)
        return filename or "upload.csv", buf.getvalue()

    # DataFrame via narwhals (supports polars, pandas, modin, …)
    try:
        import narwhals as nw
    except ImportError:
        raise ImportError(
            "narwhals is required to pass a DataFrame; "
            "install it with: pip install reportnet-client[dataframe]"
        ) from None

    try:
        native = nw.to_native(nw.from_native(file, eager_only=True))  # type: ignore[call-overload]
    except TypeError:
        raise TypeError(f"Unsupported file type: {type(file).__name__}") from None

    # Polars: write_csv() accepts a `separator` kwarg
    if hasattr(native, "write_csv"):
        result = native.write_csv(separator=delimiter)
        return filename or "upload.csv", result.encode() if isinstance(result, str) else result

    # Pandas-like: to_csv() accepts `sep`
    buf = io.BytesIO()
    native.to_csv(buf, index=False, sep=delimiter)
    return filename or "upload.csv", buf.getvalue()


def zip_to_frames(zip_bytes: bytes) -> dict[str, Any]:
    """Unzip a ZIP export and return a dict of DataFrames keyed by table name.

    Handles three formats:

    - **ZIP of CSVs** (v4 / BigData exports): one ``.csv`` file per table.
    - **ZIP of Parquet** (v5 exports): flat files or nested table partitions.
    - **ZIP of JSON** (v3 / Citus exports): a single ``.json`` file containing
      all tables in the Reportnet ETL JSON envelope.

    Requires polars or pandas (``pip install reportnet-client[dataframe]``).
    Tries polars first; falls back to pandas if polars is not installed.
    Reading Parquet (v5) with the pandas backend additionally requires
    ``pyarrow`` or ``fastparquet``; polars reads Parquet natively.
    """
    try:
        import polars as pl

        def _read_csv(data: bytes) -> Any:
            if not data.strip():
                # Reportnet emits a zero-byte CSV for a table with no rows;
                # polars raises NoDataError on it. One empty table must not
                # sink the whole export.
                return pl.DataFrame()
            return pl.read_csv(io.BytesIO(data))

        def _read_parquet(data: bytes) -> Any:
            return pl.read_parquet(io.BytesIO(data))

        def _concat_frames(frames: list[Any]) -> Any:
            return pl.concat(frames)

        def _records_to_frame(rows: list[dict[str, Any]]) -> Any:
            return pl.DataFrame(rows)

    except ImportError:
        try:
            import pandas as pd

            def _read_csv(data: bytes) -> Any:
                if not data.strip():
                    return pd.DataFrame()
                return pd.read_csv(io.BytesIO(data))

            def _read_parquet(data: bytes) -> Any:
                return pd.read_parquet(io.BytesIO(data))

            def _concat_frames(frames: list[Any]) -> Any:
                return pd.concat(frames, ignore_index=True)

            def _records_to_frame(rows: list[dict[str, Any]]) -> Any:
                return pd.DataFrame(rows)

        except ImportError:
            raise ImportError(
                "polars or pandas is required to read DataFrames; "
                "install with: pip install reportnet-client[dataframe]"
            ) from None

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        csv_names = [n for n in names if n.lower().endswith(".csv")]
        parquet_names = [n for n in names if n.lower().endswith(".parquet")]
        json_names = [n for n in names if n.lower().endswith(".json")]

        if csv_names:
            return {_table_name(n): _read_csv(zf.read(n)) for n in csv_names}

        if parquet_names:
            tables: dict[str, list[Any]] = {}
            for name in parquet_names:
                table = _parquet_table_name(name)
                tables.setdefault(table, []).append(_read_parquet(zf.read(name)))
            return {
                table: parts[0] if len(parts) == 1 else _concat_frames(parts)
                for table, parts in tables.items()
            }

        if json_names:
            return _etl_json_to_frames(zf.read(json_names[0]), _records_to_frame)

    return {}


def _table_name(path: str) -> str:
    """'some/path/TableName.csv' → 'TableName' (works for any extension)."""
    leaf = path.rsplit("/", 1)[-1]
    return leaf.rsplit(".", 1)[0] if "." in leaf else leaf


def _parquet_table_name(path: str) -> str:
    """Recognise RN3's Table/Table_<UUID>/partition.parquet layout.

    Partition filenames repeat across tables. Using the leaf name silently
    overwrites tables; all partitions belonging to a table must be combined.
    Keep supporting flat exports and archives with an outer directory.
    """
    from uuid import UUID

    parts = path.split("/")
    for table, directory in zip(parts[:-2], parts[1:-1]):
        prefix = table + "_"
        if directory.startswith(prefix):
            try:
                UUID(directory[len(prefix):])
            except ValueError:
                continue
            return table
    return _table_name(path)


def _etl_json_to_frames(
    json_bytes: bytes,
    records_to_frame: Any,
) -> dict[str, Any]:
    """Parse a v3 ETL JSON export into DataFrames.

    The JSON envelope is::

        {"tables": [{"tableName": "...", "totalRecords": N,
                     "records": [{"fields": [{"fieldName": "...", "value": "..."}]}]}]}
    """
    import json

    data = json.loads(json_bytes)
    result: dict[str, Any] = {}
    for table in data.get("tables", []):
        name: str = table["tableName"]
        rows = [
            {f["fieldName"]: f["value"] for f in rec.get("fields", [])}
            for rec in table.get("records", [])
        ]
        result[name] = records_to_frame(rows)
    return result


# ── Schema → DataFrame ────────────────────────────────────────────────────────

# Reportnet FieldType value → narwhals dtype.  Unlisted types default to nw.String.
def _nw_dtype_map() -> dict[str, Any]:
    import narwhals as nw
    return {
        "NUMBER_INTEGER": nw.Int64,
        "NUMBER_DECIMAL": nw.Float64,
        "DATE": nw.Date,
        "DATETIME": nw.Datetime,
        "BOOLEAN": nw.Boolean,
        "COORDINATE_LAT": nw.Float64,
        "COORDINATE_LONG": nw.Float64,
    }


def table_to_frame(
    table_schema: Any,
    *,
    codelists: dict[str, list[str]] | None = None,
) -> NativeFrame:
    """Return an empty DataFrame whose columns and types match *table_schema*.

    Requires ``pip install reportnet-client[dataframe]``.
    Tries polars as the backend first; falls back to pandas.

    Args:
        table_schema: A :class:`~reportnet.TableSchema` instance.
        codelists: Optional mapping of field name → valid values.  When provided,
            LINK columns use ``nw.Enum`` (backed by ``pl.Enum`` in polars or
            ``CategoricalDtype`` in pandas) instead of plain strings.

    Returns:
        A ``polars.DataFrame`` if polars is installed, otherwise a ``pandas.DataFrame``.
    """
    try:
        import narwhals as nw
    except ImportError:
        raise ImportError(
            "narwhals is required; install with: pip install reportnet-client[dataframe]"
        ) from None

    dtype_map = _nw_dtype_map()

    def _dtype(name: str, ftype: str) -> Any:
        if codelists and name in codelists:
            return nw.Enum(codelists[name])
        return dtype_map.get(ftype, nw.String)

    schema = nw.Schema({f.name: _dtype(f.name, str(f.type.value)) for f in table_schema.fields})
    data: dict[str, list[Any]] = {f.name: [] for f in table_schema.fields}

    try:
        import polars as pl
        return nw.from_dict(data, schema=schema, backend=pl).to_native()
    except ImportError:
        pass

    try:
        import pandas as pd
        return nw.from_dict(data, schema=schema, backend=pd).to_native()
    except ImportError:
        pass

    raise ImportError(
        "polars or pandas is required; install with: pip install reportnet-client[dataframe]"
    )


def cast_frame(
    table_schema: Any,
    frame: object,
    *,
    codelists: dict[str, list[str]] | None = None,
) -> NativeFrame:
    """Cast *frame* columns to the types defined in *table_schema* and validate.

    Useful when reading from Excel or CSV where all columns arrive as strings:
    numeric, date, and boolean columns are coerced to their schema types; LINK /
    CODELIST columns are cast to ``Enum`` when *codelists* is provided.

    Raises :class:`ValueError` if any required columns are missing after casting.
    Enum-cast failures also surface as ``ValueError`` with a clear message.

    Args:
        table_schema: A :class:`~reportnet.TableSchema` instance.
        frame: A polars or pandas DataFrame (any narwhals-compatible backend).
        codelists: Optional mapping returned by
            :meth:`~reportnet.DataflowClient.get_codelists`.  When provided,
            LINK columns are cast to ``Enum`` so invalid values fail loudly.

    Returns:
        The cast DataFrame in the same backend as the input.

    Example::

        import polars as pl

        raw = pl.read_excel("my_data.xlsx", sheet_name="Table1a")
        # raw["cyear"] is Float64 from Excel, but schema requires Int64
        typed = schema.table("Table1a").cast_frame(raw, codelists=codelists)
        # typed["cyear"] is now Int64; LINK columns are Enum
        flow.import_file(dataset_id=..., file=typed)
    """
    try:
        import narwhals as nw
    except ImportError:
        raise ImportError(
            "narwhals is required; install with: pip install reportnet-client[dataframe]"
        ) from None

    dtype_map = _nw_dtype_map()
    nwf = nw.from_native(frame, eager_only=True)  # type: ignore[call-overload]

    cast_dict: dict[str, Any] = {}
    for f in table_schema.fields:
        if f.name not in nwf.columns:
            continue
        if codelists and f.name in codelists:
            cast_dict[f.name] = nw.Enum(codelists[f.name])
        else:
            cast_dict[f.name] = dtype_map.get(str(f.type.value), nw.String)

    if cast_dict:
        try:
            nwf = nwf.with_columns(
                [nw.col(col).cast(dtype) for col, dtype in cast_dict.items()]
            )
        except Exception as exc:
            raise ValueError(f"Failed to cast frame columns to schema types: {exc}") from exc

    errors: list[str] = []
    frame_cols = set(nwf.columns)
    for f in table_schema.fields:
        if f.required and f.name not in frame_cols:
            errors.append(f"Required column missing: {f.name!r} (type: {f.type.value})")

    if errors:
        raise ValueError(
            "Frame does not match schema:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    return nw.to_native(nwf)


@dataclass(frozen=True)
class CodelistResolution:
    """Outcome of resolving LINK/CODELIST fields against a reference dataset.

    Carries not just the values but *what could not be resolved*, so callers
    can tell a complete answer from a partial one. Silently returning a partial
    mapping is the dangerous case: the resulting template looks identical to a
    good one but enforces nothing.
    """

    values: dict[str, list[str]]
    resolved: tuple[str, ...]
    unresolved: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return not self.unresolved

    def summary(self) -> str:
        total = len(self.resolved) + len(self.unresolved)
        if total == 0:
            return "no LINK/CODELIST fields in this dataset"
        text = f"resolved {len(self.resolved)}/{total} LINK/CODELIST field(s)"
        if self.unresolved:
            text += f"; unresolved: {sorted(self.unresolved)}"
        return text


def linked_field_names(reporting_schema: Any) -> list[str]:
    """Names of every field in *reporting_schema* that references another dataset."""
    return [
        f.name
        for table in reporting_schema.tables
        for f in table.fields
        if f.referenced_pk_id
    ]


def reference_coverage(reporting_schema: Any, ref_schema: Any) -> int:
    """How many of *reporting_schema*'s LINK fields *ref_schema* can satisfy.

    Uses schema IDs only — no data export — so this is cheap enough to run
    against every reference dataset in a dataflow to find the right one.
    """
    pk_ids = {f.id for table in ref_schema.tables for f in table.fields}
    return sum(
        1
        for table in reporting_schema.tables
        for f in table.fields
        if f.referenced_pk_id and f.referenced_pk_id in pk_ids
    )


def build_codelists(
    reporting_schema: Any,
    ref_schema: Any,
    ref_frames: dict[str, Any],
) -> CodelistResolution:
    """Map each LINK field in *reporting_schema* to its valid values.

    Looks up each LINK field's ``referenced_pk_id`` in *ref_schema* to find
    which column holds the valid values, then pulls unique sorted values from
    the corresponding table in *ref_frames*.

    Args:
        reporting_schema: :class:`~reportnet.DatasetSchema` for the reporting dataset.
        ref_schema: :class:`~reportnet.DatasetSchema` for the reference dataset.
        ref_frames: dict of DataFrames from ``etl_export().to_frames()`` on the
            reference dataset (keyed by table name).

    Returns:
        A :class:`CodelistResolution` reporting both the resolved values and
        the fields that could not be resolved.
    """
    # Build map: field schema ID → (table_name, column_name) in the reference dataset
    pk_map: dict[str, tuple[str, str]] = {}
    for table in ref_schema.tables:
        for ref_field in table.fields:
            pk_map[ref_field.id] = (table.name, ref_field.name)

    import narwhals as nw

    codelists: dict[str, list[str]] = {}
    unresolved: list[str] = []
    for table in reporting_schema.tables:
        for f in table.fields:
            if not f.referenced_pk_id:
                continue
            location = pk_map.get(f.referenced_pk_id)
            if location is None:
                # The referenced PK lives in a different reference dataset.
                unresolved.append(f.name)
                continue
            ref_table_name, ref_col_name = location
            frame = ref_frames.get(ref_table_name)
            if frame is None:
                # Schema says the table exists, but the export didn't contain it.
                unresolved.append(f.name)
                continue
            nwf = nw.from_native(frame, eager_only=True)
            if ref_col_name not in nwf.columns:
                # Reportnet exports a zero-column CSV for a table with no rows,
                # so the schema promises columns the export doesn't carry.
                unresolved.append(f.name)
                continue
            col = nwf[ref_col_name]
            values: list[Any] = col.drop_nulls().unique().sort().to_list()
            if not values:
                # An empty codelist would become Enum([]), which rejects every
                # value — worse than leaving the column as a plain string.
                unresolved.append(f.name)
                continue
            codelists[f.name] = [str(v) for v in values]

    return CodelistResolution(
        values=codelists,
        resolved=tuple(codelists),
        unresolved=tuple(dict.fromkeys(unresolved)),
    )


def _srid_mismatch(values: list[Any], crs: str) -> str | None:
    """Return a warning message if the EWKB carries a different SRID than *crs*.

    RN3 v5 exports are EWKB and carry their own SRID — 4258, not 4326, on
    dataflow 2003. ``GeoSeries.from_wkb`` discards it and stamps whatever *crs*
    says, which mislabels every coordinate with no indication. The SRID is
    sitting in the bytes, so read it rather than degrading silently.
    """
    try:
        import shapely  # type: ignore[import-untyped]

        srids = {int(shapely.get_srid(g)) for g in shapely.from_wkb(values) if g is not None}
    except Exception:  # unreadable geometry is the caller's problem, not ours
        return None
    srids.discard(0)  # 0 means "no SRID recorded", which is not a mismatch
    if not srids:
        return None
    try:
        from pyproj import CRS

        requested = CRS.from_user_input(crs).to_epsg()
    except Exception:
        requested = None
    if requested is not None and srids == {requested}:
        return None
    embedded = ", ".join(f"EPSG:{s}" for s in sorted(srids))
    return (
        f"geometry is encoded as {embedded} but to_geodataframe() was asked to assign "
        f"{crs}; coordinates are not reprojected, so the result would be mislabelled. "
        f"Pass crs=\"{embedded}\" to record the true CRS."
    )


def to_geodataframe(
    frame: object,
    geometry_col: str,
    *,
    crs: str = "EPSG:4326",
) -> Any:
    """Convert WKT, GeoJSON or WKB geometry to a ``geopandas.GeoDataFrame``.

    Geometry fields (``POINT``, ``POLYGON``, ``MULTIPOLYGON``, etc.) are stored
    as WKT/GeoJSON strings in CSV or WKB bytes in Parquet. This helper parses them into
    proper shapely geometry objects and returns a ``GeoDataFrame`` ready for
    spatial analysis or visualisation.

    Requires ``pip install reportnet-client[spatial]``.

    Args:
        frame: A polars or pandas DataFrame containing a geometry column,
            typically from :meth:`~reportnet.JobHandle.to_frames`.
        geometry_col: Name of the column holding encoded geometries
            (e.g. ``"geometry_polygon"`` or ``"geometry_line"``).
        crs: Coordinate reference system to assign, not a reprojection.
            Defaults to WGS 84 for compatibility; pass the dataset's actual
            CRS (e.g. ``"EPSG:4258"`` for dataflow 2003's spatial data).
            WKB/EWKB input carries its own SRID: when it disagrees with *crs*
            a warning is issued and logged naming the encoded CRS, because
            assigning the wrong one mislabels every coordinate silently.

    Returns:
        A ``geopandas.GeoDataFrame`` with the named column replaced by a
        proper geometry series.

    Example::

        frames = flow.etl_export(dataset_id=89259).to_frames()
        gdf = reportnet.to_geodataframe(frames["ProtectedArea"], "geometry_polygon")
        gdf.plot()
    """
    try:
        import geopandas as gpd  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "geopandas is required; install it with: pip install reportnet-client[spatial]"
        ) from None

    try:
        import narwhals as nw
        import pandas as _pd
        nwf = nw.from_native(frame, eager_only=True)  # type: ignore[call-overload]
        try:
            pdf = nwf.to_pandas()
        except Exception:
            # polars → pandas without pyarrow: go via Python lists
            pdf = _pd.DataFrame({col: nwf[col].to_list() for col in nwf.columns})
    except Exception:
        pdf = frame

    # v5 exports use WKB, including zero-length bytes for missing geometries.
    # Classify the encoding in a single pass — the column can be large, and the
    # old code scanned it twice on every non-WKB call.
    col = pdf[geometry_col]
    has_bytes = False
    first_valid: Any = None
    for value in col:
        if isinstance(value, bytes):
            has_bytes = True
            if value:
                first_valid = value
                break
        elif first_valid is None and isinstance(value, str) and value:
            first_valid = value
    if has_bytes:
        wkb_values = [v if v else None for v in col]
        mismatch = _srid_mismatch(wkb_values, crs)
        if mismatch is not None:
            logger.warning(mismatch)
            warnings.warn(mismatch, UserWarning, stacklevel=2)
        geom_series = gpd.GeoSeries.from_wkb(wkb_values, index=col.index, crs=crs)
    elif first_valid and first_valid.lstrip().startswith("{"):
        import json as _json

        from shapely.geometry import shape as _shape  # type: ignore[import-untyped]

        def _parse(val: Any) -> Any:
            if not val or not isinstance(val, str):
                return None
            try:
                obj = _json.loads(val)
                return _shape(obj.get("geometry") or obj)
            except Exception:
                return None

        geom_series = gpd.GeoSeries([_parse(v) for v in col], crs=crs)
    else:
        geom_series = gpd.GeoSeries.from_wkt(col, crs=crs)

    # Replace the raw string column with parsed geometries (keeps column count the same).
    pdf = pdf.copy()
    pdf[geometry_col] = geom_series
    return gpd.GeoDataFrame(pdf, geometry=geometry_col, crs=crs)
