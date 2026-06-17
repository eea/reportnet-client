from __future__ import annotations

import io
from pathlib import Path
from typing import IO, Union


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
