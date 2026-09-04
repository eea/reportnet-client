"""Tests for packaging metadata and the module layout.

These guard the parts of the distribution that are easy to break silently:
the PEP 561 typing marker, the exported version, and the back-compat aliases
left behind when JobHandle / connect_interactive moved modules.
"""
import importlib.metadata
from pathlib import Path

import pytest

import reportnet


def test_py_typed_marker_is_present_in_the_source_tree():
    """Without this file, downstream type checkers ignore our annotations."""
    marker = Path(reportnet.__file__).parent / "py.typed"
    assert marker.is_file(), "PEP 561 marker missing — annotations are invisible downstream"


def test_py_typed_marker_ships_in_the_installed_distribution():
    files = list(importlib.metadata.files("reportnet-client") or [])
    # An editable install records only the loader shim, not the package
    # contents, so there is nothing meaningful to assert against.
    if not any(f.name == "client.py" for f in files):
        pytest.skip("editable install — wheel contents are not recorded")
    assert any(f.name == "py.typed" for f in files), (
        "py.typed is not packaged; add it to the wheel contents"
    )


def test_version_is_exported_and_matches_distribution_metadata():
    assert reportnet.__version__ == importlib.metadata.version("reportnet-client")


def test_distribution_declares_a_licence():
    meta = importlib.metadata.metadata("reportnet-client")
    declared = meta.get("License-Expression") or meta.get("License") or ""
    assert "EUPL" in declared, f"unexpected licence metadata: {declared!r}"


# ── module layout / back-compat ───────────────────────────────────────────────
# JobHandle and JobStatus moved to reportnet.jobs; connect_interactive moved to
# reportnet.interactive; the mermaid renderer moved to reportnet.viz. The
# top-level names must keep working regardless.

def test_job_types_are_importable_from_their_old_home():
    from reportnet.jobs import JobHandle, JobStatus
    from reportnet.models import JobHandle as LegacyJobHandle
    from reportnet.models import JobStatus as LegacyJobStatus

    assert LegacyJobHandle is JobHandle
    assert LegacyJobStatus is JobStatus


def test_top_level_exports_survive_the_module_split():
    from reportnet.interactive import connect_interactive
    from reportnet.jobs import JobHandle
    from reportnet.viz import dataflow_to_mermaid

    assert reportnet.connect_interactive is connect_interactive
    assert reportnet.JobHandle is JobHandle
    assert reportnet.dataflow_to_mermaid is dataflow_to_mermaid


def test_all_exported_names_actually_resolve():
    missing = [name for name in reportnet.__all__ if not hasattr(reportnet, name)]
    assert not missing, f"__all__ lists names that don't exist: {missing}"


def test_models_module_holds_no_network_code():
    """models.py is parsed data only — the HTTP session belongs in jobs.py."""
    import reportnet.models as models

    source = Path(models.__file__).read_text()
    assert "time.sleep" not in source
    assert "HttpSession" not in source


def test_every_public_model_is_re_exported_at_top_level():
    """`reportnet.X` must work for everything models.py declares public.

    test_all_exported_names_actually_resolve checks the other direction only
    (that reportnet.__all__ resolves), so a new dataclass added to
    models.__all__ and forgotten in __init__.py passes both mypy and ruff and
    fails only for the user at the import line.
    """
    import reportnet.models as models

    missing = [name for name in models.__all__ if not hasattr(reportnet, name)]
    assert not missing, (
        f"models.__all__ exports {missing}, which reportnet does not re-export — "
        f"add them to src/reportnet/__init__.py"
    )
