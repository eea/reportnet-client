from __future__ import annotations

from typing import Any

_SERVICE = "reportnet"
_SERVICE_SANDBOX = "reportnet-sandbox"


def _keyring() -> Any:
    try:
        import keyring
        return keyring
    except ImportError:
        raise ImportError(
            "keyring is required; install it with: pip install reportnet[keyring]"
        ) from None


def _service(sandbox: bool) -> str:
    return _SERVICE_SANDBOX if sandbox else _SERVICE


def save_key(dataflow_id: int | str, api_key: str, *, sandbox: bool = False) -> None:
    """Store an API key for a dataflow in the system keychain.

    Pass ``sandbox=True`` to store a sandbox key separately from the production key.

    Raises:
        ValueError: If *api_key* is empty or whitespace-only — storing a blank
            key would silently corrupt every future request made with it.
    """
    if not api_key or not api_key.strip():
        raise ValueError("api_key must not be empty or whitespace-only.")
    _keyring().set_password(_service(sandbox), str(dataflow_id), api_key)


def get_key(dataflow_id: int | str, *, sandbox: bool = False) -> str:
    """Retrieve an API key for a dataflow from the system keychain.

    Pass ``sandbox=True`` to retrieve the sandbox key.

    A blank (empty or whitespace-only) stored value is treated the same as
    "not found" — it can only have gotten there via a caller that bypassed
    :func:`save_key`'s validation, and silently using it would produce a
    malformed ``Authorization`` header deep in the HTTP layer instead of a
    clear error here.
    """
    svc = _service(sandbox)
    key = _keyring().get_password(svc, str(dataflow_id))
    if key is None or not key.strip():
        env = "sandbox" if sandbox else "production"
        raise KeyError(
            f"No {env} API key found for dataflow {dataflow_id}. "
            f"Store one with: reportnet.save_key({dataflow_id!r}, 'your-key'"
            + (", sandbox=True" if sandbox else "")
            + ")"
        )
    return str(key)


def delete_key(dataflow_id: int | str, *, sandbox: bool = False) -> None:
    """Remove an API key for a dataflow from the system keychain.

    Pass ``sandbox=True`` to delete the sandbox key.
    """
    _keyring().delete_password(_service(sandbox), str(dataflow_id))
