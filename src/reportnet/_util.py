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
        content: bytes = file.read()  # type: ignore[union-attr]
        name: str = getattr(file, "name", None) or "upload.csv"
        return filename or name, content

    # DataFrame via narwhals (supports polars, pandas, modin, …)
    try:
        import narwhals as nw  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "narwhals is required to pass a DataFrame; install it with: pip install reportnet[dataframe]"
        ) from None

    try:
        native = nw.to_native(nw.from_native(file, eager_only=True))
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
        import polars as pl  # type: ignore[import]

        def _read(data: bytes) -> Any:
            return pl.read_csv(io.BytesIO(data))

    except ImportError:
        try:
            import pandas as pd  # type: ignore[import]

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
