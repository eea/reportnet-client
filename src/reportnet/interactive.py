"""Helpers for interactive/notebook use.

These wrap the normal client API in a non-raising, UI-friendly shape.  They are
deliberately separate from :mod:`reportnet.client`: presentation concerns don't
belong in the transport layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dataflow import DataflowClient


def connect_interactive(
    dataflow_id: int,
    *,
    sandbox: bool = False,
    country_code: str | None = None,
) -> tuple["DataflowClient | None", str | None]:
    """Connect for interactive/notebook use, returning a UI-ready result.

    Loads the API key from the system keychain and builds a
    :class:`~reportnet.DataflowClient` scoped to *dataflow_id*. When
    *country_code* is given, further scopes it to that reporter via
    :meth:`~reportnet.DataflowClient.find_reporter`. When *country_code* is
    omitted, validates the key with a single
    :meth:`~reportnet.DataflowClient.ping` call instead (there's no specific
    reporter to resolve).

    This exists mainly to back the "Connect" cell shared by the example
    marimo notebooks under ``notebooks/`` — see there for usage — but is
    generally useful for any interactive tool that wants a one-call,
    non-raising connect step.

    Args:
        dataflow_id: The dataflow to connect to.
        sandbox: Use the sandbox environment and sandbox key.
        country_code: ISO 3166-1 alpha-2 code to scope to a specific reporter.

    Returns:
        ``(flow, error_message)``. On success, ``error_message`` is
        ``None``. On failure, ``flow`` is ``None`` and ``error_message`` is
        a short, human-readable string safe to show directly in a UI
        callout.

    Example::

        flow, error = reportnet.connect_interactive(1619, country_code="IE")
        if error:
            mo.callout(mo.md(error), kind="danger")
        else:
            mo.callout(mo.md(f"Connected — provider_id={flow._provider_id}"), kind="success")
    """
    from .client import ReportnetClient
    from .exceptions import AuthError

    try:
        client = ReportnetClient.from_keyring(dataflow_id, sandbox=sandbox)
        flow = client.for_dataflow(dataflow_id)
        if country_code:
            return flow.find_reporter(country_code), None
        if not flow.ping():
            return None, "API key is invalid or has been revoked."
        return flow, None
    except KeyError:
        env = "sandbox" if sandbox else "production"
        return None, (
            f"No {env} API key found for dataflow {dataflow_id}. "
            "Expand *Save API key* above to store your key."
        )
    except ValueError as exc:
        return None, f"Country lookup failed: {exc}"
    except AuthError:
        return None, "API key is invalid or has been revoked."
