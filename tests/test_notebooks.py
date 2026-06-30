"""Smoke tests for the marimo notebooks.

Verifies each notebook parses and exports a valid marimo App object.
These tests do NOT execute cells or make network calls.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

NOTEBOOKS_DIR = Path(__file__).parent.parent / "notebooks"
NOTEBOOKS = sorted(NOTEBOOKS_DIR.glob("*.py"))


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
def test_notebook_is_valid_marimo_app(path):
    marimo = pytest.importorskip("marimo")

    spec = importlib.util.spec_from_file_location(f"_nb_{path.stem}", path)
    assert spec is not None and spec.loader is not None, f"Cannot load {path}"

    module = importlib.util.module_from_spec(spec)
    # Add to sys.modules under a temporary name so imports inside the notebook work
    tmp_name = f"_nb_{path.stem}"
    sys.modules[tmp_name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        sys.modules.pop(tmp_name, None)

    assert hasattr(module, "app"), f"{path.name} does not define an `app` variable"
    assert isinstance(module.app, marimo.App), (
        f"{path.name}.app is {type(module.app).__name__}, expected marimo.App"
    )
