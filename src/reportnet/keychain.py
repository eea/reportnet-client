from __future__ import annotations

from typing import Any

_SERVICE = "reportnet"


def _keyring() -> Any:
    try:
        import keyring
        return keyring
    except ImportError:
        raise ImportError(
            "keyring is required; install it with: pip install reportnet[keyring]"
        ) from None


def save_key(dataflow_id: int | str, api_key: str) -> None:
    """Store an API key for a dataflow in the system keychain."""
    _keyring().set_password(_SERVICE, str(dataflow_id), api_key)


def get_key(dataflow_id: int | str) -> str:
    """Retrieve an API key for a dataflow from the system keychain."""
    key = _keyring().get_password(_SERVICE, str(dataflow_id))
    if key is None:
        raise KeyError(
            f"No API key found for dataflow {dataflow_id}. "
            f"Store one with: reportnet.save_key({dataflow_id!r}, 'your-key')"
        )
    return str(key)


def delete_key(dataflow_id: int | str) -> None:
    """Remove an API key for a dataflow from the system keychain."""
    _keyring().delete_password(_SERVICE, str(dataflow_id))
