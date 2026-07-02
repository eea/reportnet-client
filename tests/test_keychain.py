"""Tests for reportnet.keychain — uses an in-memory fake, never the real OS keychain."""
from unittest.mock import patch

import pytest

from reportnet import keychain


class _FakeKeyring:
    """Minimal in-memory stand-in for the `keyring` package."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        del self._store[(service, username)]


@pytest.fixture
def fake_keyring():
    fake = _FakeKeyring()
    with patch.object(keychain, "_keyring", return_value=fake):
        yield fake


def test_save_and_get_key_round_trip(fake_keyring):
    keychain.save_key(1619, "real-key")
    assert keychain.get_key(1619) == "real-key"


def test_save_and_get_key_sandbox_is_separate(fake_keyring):
    keychain.save_key(1619, "prod-key")
    keychain.save_key(1619, "sandbox-key", sandbox=True)
    assert keychain.get_key(1619) == "prod-key"
    assert keychain.get_key(1619, sandbox=True) == "sandbox-key"


def test_save_key_rejects_empty_string(fake_keyring):
    with pytest.raises(ValueError, match="empty"):
        keychain.save_key(1619, "")


def test_save_key_rejects_whitespace_only(fake_keyring):
    with pytest.raises(ValueError, match="empty"):
        keychain.save_key(1619, "   ")


def test_get_key_raises_when_not_found(fake_keyring):
    with pytest.raises(KeyError, match="No production API key found for dataflow 1619"):
        keychain.get_key(1619)


def test_get_key_raises_when_stored_value_is_blank(fake_keyring):
    """A blank value can only get stored by bypassing save_key()'s validation
    (e.g. a caller writing directly via keyring, or a pre-existing corrupted
    entry) — get_key() must treat it as not-found rather than returning it,
    since using it verbatim produces a malformed Authorization header."""
    fake_keyring.set_password("reportnet", "1619", "")
    with pytest.raises(KeyError, match="No production API key found for dataflow 1619"):
        keychain.get_key(1619)

    fake_keyring.set_password("reportnet", "1619", "   ")
    with pytest.raises(KeyError, match="No production API key found for dataflow 1619"):
        keychain.get_key(1619)


def test_get_key_error_message_mentions_sandbox(fake_keyring):
    with pytest.raises(KeyError, match="No sandbox API key found for dataflow 1619"):
        keychain.get_key(1619, sandbox=True)


def test_delete_key(fake_keyring):
    keychain.save_key(1619, "real-key")
    keychain.delete_key(1619)
    with pytest.raises(KeyError):
        keychain.get_key(1619)
