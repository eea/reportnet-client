"""Login-token authentication: bearer header, refresh, rotation, no leaked secrets."""

import base64
import json
import logging
import time

import httpx
import pytest
import respx

from reportnet import ReportnetClient
from reportnet._auth import TokenAuth, TokenPair, jwt_expiry, redact
from reportnet.exceptions import AuthError

BASE = "https://api.reportnet.europa.eu"
SANDBOX = "https://sandbox-api.reportnet.europa.eu"


def make_jwt(exp: float, sub: str = "u") -> str:
    def enc(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{enc({'alg': 'none'})}.{enc({'exp': int(exp), 'sub': sub})}.sig"


def token_response(access: str, refresh: str) -> httpx.Response:
    return httpx.Response(200, json={
        "accessToken": access, "refreshToken": refresh, "roles": [], "groups": [],
        "accessTokenExpiration": None, "preferredUsername": "u", "userId": "1",
    })


@pytest.fixture
def router():
    with respx.mock(base_url=BASE, assert_all_called=False) as r:
        yield r


def test_jwt_expiry_reads_exp_without_verifying():
    assert jwt_expiry(make_jwt(1_900_000_000)) == 1_900_000_000
    assert jwt_expiry("not-a-jwt") is None
    assert jwt_expiry("a.%%%.c") is None


def test_sends_bearer_header(router):
    access = make_jwt(time.time() + 3600)
    route = router.get("/dataflow/v1/1").mock(return_value=httpx.Response(200, json={}))
    client = ReportnetClient.from_tokens(access, "rt-1")
    client._http.get("/dataflow/v1/1")
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {access}"
    assert client.auth_kind == "bearer"


def test_api_key_client_reports_api_key_kind(client):
    assert client.auth_kind == "api_key"
    assert client.tokens is None
    with pytest.raises(TypeError):
        client.refresh_tokens()


def test_refreshes_before_expiry_and_keeps_rotated_refresh_token(router):
    old = make_jwt(time.time() + 10)          # inside the 60-second margin
    new = make_jwt(time.time() + 3600, "new")
    refresh = router.post("/user/refreshToken").mock(return_value=token_response(new, "rt-2"))
    route = router.get("/x").mock(return_value=httpx.Response(200))
    seen: list[TokenPair] = []
    client = ReportnetClient.from_tokens(old, "rt-1", on_refresh=seen.append)

    client._http.get("/x")

    assert refresh.call_count == 1
    assert refresh.calls.last.request.url.params["refreshToken"] == "rt-1"
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {new}"
    assert client.tokens == TokenPair(new, "rt-2")
    assert seen == [TokenPair(new, "rt-2")]


def test_does_not_refresh_a_token_that_is_still_valid(router):
    refresh = router.post("/user/refreshToken").mock(return_value=token_response("a", "b"))
    router.get("/x").mock(return_value=httpx.Response(200))
    client = ReportnetClient.from_tokens(make_jwt(time.time() + 3600), "rt-1")
    client._http.get("/x")
    assert refresh.call_count == 0


@pytest.mark.parametrize("refusal", [
    httpx.Response(401),
    httpx.Response(500, json={"message": "status 401 reading DataflowControllerZuul#find"}),
])
def test_refreshes_once_on_401_and_resends(router, refusal):
    old, new = make_jwt(time.time() + 3600, "old"), make_jwt(time.time() + 3600, "new")
    refresh = router.post("/user/refreshToken").mock(return_value=token_response(new, "rt-2"))
    route = router.post("/dataschema/1/tableSchema").mock(
        side_effect=[refusal, httpx.Response(200, json={"idTableSchema": "t"})]
    )
    client = ReportnetClient.from_tokens(old, "rt-1")

    r = client._http.post("/dataschema/1/tableSchema", json={"nameTableSchema": "A"})

    assert r.json() == {"idTableSchema": "t"}
    assert refresh.call_count == 1
    assert route.call_count == 2
    assert route.calls[1].request.headers["Authorization"] == f"Bearer {new}"
    assert route.calls[1].request.content == route.calls[0].request.content


def test_second_401_is_raised_not_retried_again(router):
    fresh = make_jwt(time.time() + 3600, "new")
    router.post("/user/refreshToken").mock(return_value=token_response(fresh, "rt-2"))
    route = router.get("/x").mock(return_value=httpx.Response(401))
    client = ReportnetClient.from_tokens(make_jwt(time.time() + 3600), "rt-1")
    with pytest.raises(AuthError):
        client._http.get("/x")
    assert route.call_count == 2


def test_403_does_not_trigger_a_refresh(router):
    refresh = router.post("/user/refreshToken")
    router.get("/x").mock(return_value=httpx.Response(403))
    client = ReportnetClient.from_tokens(make_jwt(time.time() + 3600), "rt-1")
    with pytest.raises(AuthError):
        client._http.get("/x")
    assert refresh.call_count == 0


def test_refused_refresh_raises_auth_error_without_echoing_the_body(router):
    router.post("/user/refreshToken").mock(return_value=httpx.Response(400, text="bad rt-1"))
    auth = TokenAuth("a", "rt-1", base_url=BASE)
    with pytest.raises(AuthError) as exc:
        auth.refresh()
    assert "rt-1" not in str(exc.value)


def test_from_tokens_sandbox_uses_sandbox_api_host():
    with respx.mock(base_url=SANDBOX) as r:
        route = r.get("/dataflow/v1/11468").mock(return_value=httpx.Response(200, json={}))
        ReportnetClient.from_tokens(make_jwt(time.time() + 3600), "rt", sandbox=True)._http.get(
            "/dataflow/v1/11468"
        )
    assert route.called


def test_from_credentials_calls_generate_token(router):
    access = make_jwt(time.time() + 3600)
    gen = router.post("/user/generateToken").mock(return_value=token_response(access, "rt-9"))
    client = ReportnetClient.from_credentials("me", "s3cret")
    assert gen.calls.last.request.url.params["username"] == "me"
    assert client.tokens == TokenPair(access, "rt-9")


def test_empty_tokens_are_rejected():
    with pytest.raises(ValueError):
        ReportnetClient.from_tokens("", "rt")


def test_api_key_and_auth_together_are_rejected():
    with pytest.raises(ValueError):
        ReportnetClient(api_key="k", auth=TokenAuth("a", "b", base_url=BASE))


def test_secrets_never_reach_the_logs(router, caplog):
    old = make_jwt(time.time() + 10, "old")
    new = make_jwt(time.time() + 3600, "new")
    router.post("/user/refreshToken").mock(return_value=token_response(new, "rt-NEW"))
    router.get("/x").mock(return_value=httpx.Response(200))
    caplog.set_level(logging.DEBUG)
    client = ReportnetClient.from_tokens(old, "rt-OLD")
    client._http.get("/x")

    text = caplog.text + " ".join(str(r.args) for r in caplog.records)
    for secret in ("rt-OLD", "rt-NEW", old, new):
        assert secret not in text
    assert any("HTTP Request" in r.getMessage() for r in caplog.records)  # httpx did log


def test_redact_masks_query_secrets():
    assert redact("POST /user/refreshToken?refreshToken=abc&x=1") == (
        "POST /user/refreshToken?refreshToken=***&x=1"
    )
    assert "pw" not in redact("/user/generateToken?username=me&password=pw")


def test_capabilities_records_auth_kind(router):
    router.get("/dataflow/v1/5").mock(return_value=httpx.Response(200, json={"id": 5}))
    caps = ReportnetClient.from_tokens(make_jwt(time.time() + 3600), "rt").capabilities(
        dataflow_id=5
    )
    assert caps.auth_kind == "bearer"
    assert "login token" in caps.summary()
