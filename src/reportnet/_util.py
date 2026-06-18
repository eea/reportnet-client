from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, TypeAlias, Union

if TYPE_CHECKING:
    import pandas  # type: ignore[import-untyped]
    import polars

    NativeFrame: TypeAlias = Union[polars.DataFrame, pandas.DataFrame]


def to_file_tuple(
    file: Union[str, Path, bytes, IO[bytes], object],
    filename: str | None,
) -> tuple[str, bytes]:
    """Return (filename, bytes) for any accepted file input."""
    if isinstance(file, (str, Path)):
        path = Path(file)
        return filename or path.name, path.read_bytes()

    if isinstance(file, bytes):
        return filename or "upload.csv", file

    if hasattr(file, "read"):
        content: bytes = file.read()
        name: str = getattr(file, "name", None) or "upload.csv"
        return filename or name, content

    # DataFrame via narwhals (supports polars, pandas, modin, …)
    try:
        import narwhals as nw
    except ImportError:
        raise ImportError(
            "narwhals is required to pass a DataFrame; "
            "install it with: pip install reportnet[dataframe]"
        ) from None

    try:
        native = nw.to_native(nw.from_native(file, eager_only=True))  # type: ignore[call-overload]
    except TypeError:
        raise TypeError(f"Unsupported file type: {type(file).__name__}") from None

    # Polars: write_csv() returns a str
    if hasattr(native, "write_csv"):
        result = native.write_csv()
        return filename or "upload.csv", result.encode() if isinstance(result, str) else result

    # Pandas-like: to_csv() writes to a buffer
    buf = io.BytesIO()
    native.to_csv(buf, index=False)
    return filename or "upload.csv", buf.getvalue()


def zip_to_frames(zip_bytes: bytes) -> dict[str, Any]:
    """Unzip a ZIP of CSVs and return a dict of DataFrames keyed by table name.

    Requires polars or pandas (``pip install reportnet[dataframe]``).
    Tries polars first; falls back to pandas if polars is not installed.
    """
    try:
        import polars as pl

        def _read(data: bytes) -> Any:
            return pl.read_csv(io.BytesIO(data))

    except ImportError:
        try:
            import pandas as pd

            def _read(data: bytes) -> Any:
                return pd.read_csv(io.BytesIO(data))

        except ImportError:
            raise ImportError(
                "polars or pandas is required to read DataFrames; "
                "install with: pip install reportnet[dataframe]"
            ) from None

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return {
            _table_name(name): _read(zf.read(name))
            for name in zf.namelist()
            if name.lower().endswith(".csv")
        }


def _table_name(path: str) -> str:
    """'some/path/TableName.csv' → 'TableName'"""
    leaf = path.rsplit("/", 1)[-1]
    return leaf[:-4] if leaf.lower().endswith(".csv") else leaf


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

    Requires ``pip install reportnet[dataframe]``.
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
            "narwhals is required; install with: pip install reportnet[dataframe]"
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
        "polars or pandas is required; install with: pip install reportnet[dataframe]"
    )


def build_codelists(
    reporting_schema: Any,
    ref_schema: Any,
    ref_frames: dict[str, Any],
) -> dict[str, list[str]]:
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
        A dict mapping field name → sorted list of valid string values.
        Only LINK fields whose ``referenced_pk_id`` matches a field in *ref_schema*
        are included.
    """
    # Build map: field schema ID → (table_name, column_name) in the reference dataset
    pk_map: dict[str, tuple[str, str]] = {}
    for table in ref_schema.tables:
        for ref_field in table.fields:
            pk_map[ref_field.id] = (table.name, ref_field.name)

    codelists: dict[str, list[str]] = {}
    for table in reporting_schema.tables:
        for f in table.fields:
            if not f.referenced_pk_id:
                continue
            location = pk_map.get(f.referenced_pk_id)
            if location is None:
                continue
            ref_table_name, ref_col_name = location
            frame = ref_frames.get(ref_table_name)
            if frame is None:
                continue
            col = frame[ref_col_name]
            if hasattr(col, "drop_nulls"):  # polars Series
                values: list[Any] = col.drop_nulls().unique().sort().to_list()
            else:  # pandas Series
                values = sorted(col.dropna().unique().tolist())
            codelists[f.name] = [str(v) for v in values]

    return codelists
