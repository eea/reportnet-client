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

    # pandas DataFrame — optional dependency
    try:
        import pandas as pd  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "pandas is required to pass a DataFrame; install it with: pip install reportnet[pandas]"
        ) from None

    if isinstance(file, pd.DataFrame):
        buf = io.BytesIO()
        file.to_csv(buf, index=False)
        return filename or "upload.csv", buf.getvalue()

    raise TypeError(f"Unsupported file type: {type(file).__name__}")
