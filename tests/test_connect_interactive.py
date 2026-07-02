"""Tests for reportnet.connect_interactive() — the shared notebook connect helper."""
from unittest.mock import patch

import httpx
import pytest

import reportnet
from reportnet.dataflow import DataflowClient

DATAFLOW_RESPONSE = {
    "id": 1619, "name": "EU GHG Inventory", "description": "", "type": "REPORTING",
    "status": "PUBLIC",
}
REPORTERS_RESPONSE = [
    {"id": 10, "dataProviderId": 17},   # IE (Ireland)
]


def _patch_key(key: str = "test-key"):
    return patch("reportnet.keychain.get_key", return_value=key)


def test_connect_interactive_success_no_country_code(mock_router):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    with _patch_key():
        flow, error = reportnet.connect_interactive(1619)
    assert error is None
    assert isinstance(flow, DataflowClient)
    assert flow._provider_id is None


def test_connect_interactive_invalid_key_message_on_failed_ping(mock_router):
    mock_router.get("/dataflow/v1/1619").mock(return_value=httpx.Response(401))
    with _patch_key():
        flow, error = reportnet.connect_interactive(1619)
    assert flow is None
    assert error == "API key is invalid or has been revoked."


def test_connect_interactive_missing_key_returns_message():
    with patch("reportnet.keychain.get_key", side_effect=KeyError("no key")):
        flow, error = reportnet.connect_interactive(1619)
    assert flow is None
    assert "No production API key found for dataflow 1619" in error


def test_connect_interactive_missing_key_mentions_sandbox():
    with patch("reportnet.keychain.get_key", side_effect=KeyError("no key")):
        flow, error = reportnet.connect_interactive(1619, sandbox=True)
    assert "No sandbox API key found for dataflow 1619" in error


def test_connect_interactive_with_country_code_success(mock_router):
    # /dataflow/v1/1619 is deliberately left unmocked: with a country_code,
    # connect_interactive() should resolve via find_reporter() alone and never
    # call ping() — if it did, this request would hit the unmocked route and
    # respx would raise.
    route = mock_router.get("/representative/v1/dataflow/1619").mock(
        return_value=httpx.Response(200, json=REPORTERS_RESPONSE)
    )
    with _patch_key():
        flow, error = reportnet.connect_interactive(1619, country_code="IE")
    assert error is None
    assert isinstance(flow, DataflowClient)
    assert flow._provider_id == 17
    assert route.called


def test_connect_interactive_unknown_country_code_returns_message(mock_router):
    mock_router.get("/representative/v1/dataflow/1619").mock(
        return_value=httpx.Response(200, json=REPORTERS_RESPONSE)
    )
    with _patch_key():
        flow, error = reportnet.connect_interactive(1619, country_code="XX")
    assert flow is None
    assert error.startswith("Country lookup failed:")
    assert "XX" in error


def test_connect_interactive_auth_error_with_country_code(mock_router):
    mock_router.get("/representative/v1/dataflow/1619").mock(return_value=httpx.Response(401))
    with _patch_key():
        flow, error = reportnet.connect_interactive(1619, country_code="IE")
    assert flow is None
    assert error == "API key is invalid or has been revoked."


@pytest.mark.parametrize("sandbox", [False, True])
def test_connect_interactive_passes_sandbox_flag_to_keyring(mock_router, sandbox):
    url = (
        "https://sandbox.reportnet.europa.eu/dataflow/v1/1619"
        if sandbox
        else "/dataflow/v1/1619"
    )
    mock_router.get(url).mock(return_value=httpx.Response(200, json=DATAFLOW_RESPONSE))
    with patch("reportnet.keychain.get_key", return_value="test-key") as mock_get_key:
        reportnet.connect_interactive(1619, sandbox=sandbox)
    mock_get_key.assert_called_once_with(1619, sandbox=sandbox)
