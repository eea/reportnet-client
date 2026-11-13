"""A dead login-token pair must surface as LoginTokenError, not as a key-scope problem.

Seen live on sandbox 11468, 2026-11-12: a stale pair copied from the web app
got 401, the renewal got HTTP 500 (Reportnet's answer to any invalid refresh
token), and the client reported "Reporter keys must identify which provider
they are reading for", which sent the user looking in the wrong place.
"""

import httpx
import pytest
import respx

from reportnet import ReportnetClient
from reportnet.exceptions import AuthError, DiscoveryNotPermittedError

BASE = "https://api.reportnet.europa.eu"


@pytest.fixture
def dead_pair():
    with respx.mock(base_url=BASE, assert_all_called=False) as r:
        r.get(url__regex=r"/dataflow/v1/\d+.*").mock(return_value=httpx.Response(401))
        r.get(url__regex=r"/representative/.*").mock(return_value=httpx.Response(401))
        r.post("/user/refreshToken").mock(return_value=httpx.Response(500, text="boom"))
        yield r


def _assert_login_token_error(exc: BaseException) -> None:
    assert isinstance(exc, AuthError)
    assert type(exc).__name__ == "LoginTokenError"
    assert not isinstance(exc, DiscoveryNotPermittedError)
    message = str(exc).lower()
    assert "reporter" not in message
    assert "log in again" in message


def test_dataflow_read_reports_a_dead_token_pair(dead_pair):
    flow = ReportnetClient.from_tokens("at-old", "rt-old").for_dataflow(11468)
    with pytest.raises(AuthError) as info:
        flow.get_dataflow_contents()
    _assert_login_token_error(info.value)


def test_capabilities_reports_a_dead_token_pair(dead_pair):
    client = ReportnetClient.from_tokens("at-old", "rt-old")
    with pytest.raises(AuthError) as info:
        client.capabilities(dataflow_id=11468)
    _assert_login_token_error(info.value)


def test_is_big_dataflow_reports_a_dead_token_pair(dead_pair):
    client = ReportnetClient.from_tokens("at-old", "rt-old")
    with pytest.raises(AuthError) as info:
        client.is_big_dataflow(dataflow_id=11468)
    _assert_login_token_error(info.value)


def test_refused_renewal_does_not_echo_the_response_body(dead_pair):
    client = ReportnetClient.from_tokens("at-old", "rt-old")
    with pytest.raises(AuthError) as info:
        client.get_dataflow_contents(dataflow_id=11468)
    assert "boom" not in str(info.value)
    assert "rt-old" not in str(info.value)
