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
    """
    _keyring().set_password(_service(sandbox), str(dataflow_id), api_key)


def get_key(dataflow_id: int | str, *, sandbox: bool = False) -> str:
    """Retrieve an API key for a dataflow from the system keychain.

    Pass ``sandbox=True`` to retrieve the sandbox key.
    """
    svc = _service(sandbox)
    key = _keyring().get_password(svc, str(dataflow_id))
    if key is None:
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
