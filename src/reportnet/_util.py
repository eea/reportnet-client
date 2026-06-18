from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import IO, Any, Union


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
            import pandas as pd  # type: ignore[import-untyped]

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

# Reportnet FieldType value → polars dtype.  String types default to pl.String.
_POLARS_DTYPE_MAP: dict[str, str] = {
    "NUMBER_INTEGER": "Int64",
    "NUMBER_DECIMAL": "Float64",
    "DATE": "Date",
    "DATETIME": "Datetime",
    "BOOLEAN": "Boolean",
    "COORDINATE_LAT": "Float64",
    "COORDINATE_LONG": "Float64",
}

# Reportnet FieldType value → pandas dtype.  All others default to "object".
_PANDAS_DTYPE_MAP: dict[str, str] = {
    "NUMBER_INTEGER": "Int64",    # nullable integer (pandas >= 1.0)
    "NUMBER_DECIMAL": "Float64",  # nullable float
    "DATETIME": "datetime64[ns]",
    "BOOLEAN": "boolean",
    "COORDINATE_LAT": "Float64",
    "COORDINATE_LONG": "Float64",
}


def table_to_frame(table_schema: Any) -> Any:
    """Return an empty DataFrame whose columns and types match *table_schema*.

    Tries polars first; falls back to pandas.
    Requires ``pip install reportnet[dataframe]``.

    Args:
        table_schema: A :class:`~reportnet.TableSchema` instance.

    Returns:
        An empty polars or pandas DataFrame with the correct schema.
    """
    fields = [(f.name, str(f.type.value)) for f in table_schema.fields]

    try:
        import polars as pl

        schema = {
            name: getattr(pl, _POLARS_DTYPE_MAP.get(ftype, "String"))
            for name, ftype in fields
        }
        return pl.DataFrame(schema=schema)

    except ImportError:
        try:
            import pandas as pd

            return pd.DataFrame({
                name: pd.array([], dtype=_PANDAS_DTYPE_MAP.get(ftype, "object"))
                for name, ftype in fields
            })

        except ImportError:
            raise ImportError(
                "polars or pandas is required; install with: pip install reportnet[dataframe]"
            ) from None
