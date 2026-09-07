"""Tests for retry / back-off logic in HttpSession._request."""
from unittest.mock import patch

import httpx
import pytest

from reportnet import JobHandle
from reportnet.exceptions import APIError, AuthError, RateLimitError

POLLING_URL = "/orchestrator/jobs/pollForJobStatus/1?datasetId=1&dataflowId=2"
EXPORT_RESPONSE = {"pollingUrl": POLLING_URL, "status": "QUEUED"}


def _patch_sleep():
    return patch("reportnet._http.time.sleep")


def _patch_random():
    return patch("reportnet._http.random.uniform", return_value=0.0)


# ── api_key validation ───────────────────────────────────────────────────────
# A blank api_key must be rejected here, at construction time, with a clear
# error — rather than reaching httpx and failing deep in the stack with a
# cryptic "Illegal header value" from a malformed `Authorization: ApiKey `.

def test_empty_api_key_raises_value_error():
    from reportnet import ReportnetClient

    with pytest.raises(ValueError, match="empty"):
        ReportnetClient(api_key="")


def test_whitespace_only_api_key_raises_value_error():
    from reportnet import ReportnetClient

    with pytest.raises(ValueError, match="empty"):
        ReportnetClient(api_key="   ")


def test_api_key_is_stripped_of_surrounding_whitespace():
    from reportnet import ReportnetClient

    c = ReportnetClient(api_key="  real-key  ")
    assert c._http._client.headers["Authorization"] == "ApiKey real-key"


def test_get_retries_on_transport_error_then_succeeds(mock_router, client):
    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("connection reset")
        return httpx.Response(200, json=EXPORT_RESPONSE)

    with patch.object(client._http._client, "request", side_effect=mock_request):
        with _patch_sleep(), _patch_random():
            handle = client.etl_export(dataset_id=1, dataflow_id=2, version=4)

    assert call_count == 2
    assert isinstance(handle, JobHandle)


def test_get_raises_after_max_retries_on_transport_error(mock_router, client):
    with patch.object(
        client._http._client,
        "request",
        side_effect=httpx.ConnectError("unreachable"),
    ):
        with _patch_sleep(), _patch_random(), pytest.raises(httpx.ConnectError):
            client.etl_export(dataset_id=1, dataflow_id=2, version=4)


def test_get_retries_on_5xx(mock_router, client):
    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json=EXPORT_RESPONSE)

    with patch.object(client._http._client, "request", side_effect=mock_request):
        with _patch_sleep(), _patch_random():
            handle = client.etl_export(dataset_id=1, dataflow_id=2, version=4)

    assert call_count == 2
    assert isinstance(handle, JobHandle)


def test_post_does_not_retry_on_5xx(mock_router, client):
    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text="Server Error")

    with patch.object(client._http._client, "request", side_effect=mock_request):
        with pytest.raises(APIError) as exc_info:
            client.import_file(dataset_id=1, dataflow_id=2, file=b"data")

    assert exc_info.value.status_code == 500
    assert call_count == 1  # no retry on POST 5xx


def test_raises_rate_limit_error_on_429(mock_router, client):
    mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(429, text="Too Many Requests")
    )
    with pytest.raises(RateLimitError) as exc_info:
        client.import_file(dataset_id=1, dataflow_id=2, file=b"data")
    assert exc_info.value.status_code == 429


def test_raises_dataset_locked_error_on_423(mock_router, client):
    from reportnet.exceptions import DatasetLockedError

    mock_router.put("/orchestrator/jobs/addValidationJob/1").mock(
        return_value=httpx.Response(423, text="Locked")
    )
    with pytest.raises(DatasetLockedError) as exc_info:
        client.add_validation_job(dataset_id=1, dataflow_id=2)
    assert exc_info.value.status_code == 423


def test_500_wrapping_401_raises_auth_error_not_api_error(mock_router, client):
    """Reportnet gateway wraps auth failures as HTTP 500 with 'UNAUTHORIZED' in body."""
    body = '{"status":500,"error":"Internal Server Error","message":"401 UNAUTHORIZED"}'
    mock_router.get("/dataflow/v1/1").mock(return_value=httpx.Response(500, text=body))
    with pytest.raises(AuthError) as exc_info:
        client.get_dataflow(dataflow_id=1)
    assert exc_info.value.status_code == 500


def test_500_wrapping_401_is_not_retried(mock_router, client):
    """Auth-failure 500s should not be retried (unlike genuine server errors)."""
    body = '{"message":"401 UNAUTHORIZED"}'
    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text=body)

    with patch.object(client._http._client, "request", side_effect=mock_request):
        with pytest.raises(AuthError):
            client.get_dataflow(dataflow_id=1)

    assert call_count == 1  # no retry


def test_500_wrapping_401_via_status_code_string_is_not_retried(mock_router, client):
    """Same as above, but the body only contains '"401"', not the word UNAUTHORIZED.

    The retry-skip check and the exception-raising check must recognize the
    same set of wrapped-401 bodies — otherwise this variant gets retried
    (wasting up to 3 attempts with exponential back-off) before AuthError is
    finally raised.
    """
    body = '{"status":500,"error":"Internal Server Error","message":"401"}'
    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text=body)

    with patch.object(client._http._client, "request", side_effect=mock_request):
        with pytest.raises(AuthError):
            client.get_dataflow(dataflow_id=1)

    assert call_count == 1  # no retry


def test_ping_returns_false_on_500_wrapped_401(mock_router, client):
    """ping() should return False when the API key is rejected via a 500-wrapped 401."""
    body = '{"message":"401 UNAUTHORIZED","status":500}'
    mock_router.get("/dataflow/v1/1").mock(return_value=httpx.Response(500, text=body))
    assert client.ping(dataflow_id=1) is False


def test_sleep_is_called_between_retries(client):
    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.ConnectError("reset")
        return httpx.Response(200, json=EXPORT_RESPONSE)

    with patch.object(client._http._client, "request", side_effect=mock_request):
        with _patch_random(), patch("reportnet._http.time.sleep") as mock_sleep:
            client.etl_export(dataset_id=1, dataflow_id=2, version=4)

    assert mock_sleep.call_count == 2


# ── wrapped 403 ──────────────────────────────────────────────────────────────
# The gateway wraps 403s the same way it wraps 401s. Observed live on
# dataflow 2003 when importing with a read-only key:
#   {"status":500,"message":"status 403 reading JobControllerZuul#addImportJob(...)"}
# Before this was handled, that surfaced as a generic APIError *and* burned
# three retries with back-off on a permanent permission error.

WRAPPED_403_BODY = (
    '{"timestamp":1788514956397,"status":500,"error":"Internal Server Error",'
    '"message":"status 403 reading JobControllerZuul#addImportJob(Long,Long)",'
    '"path":"/dataset/v2/importFileData/108953"}'
)


def test_500_wrapping_403_raises_auth_error_not_api_error(mock_router, client):
    mock_router.get("/dataflow/v1/1").mock(
        return_value=httpx.Response(500, text=WRAPPED_403_BODY)
    )
    with pytest.raises(AuthError) as exc_info:
        client.get_dataflow(dataflow_id=1)
    assert exc_info.value.status_code == 500


def test_500_wrapping_403_is_not_retried(mock_router, client):
    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text=WRAPPED_403_BODY)

    with patch.object(client._http._client, "request", side_effect=mock_request):
        with pytest.raises(AuthError):
            client.get_dataflow(dataflow_id=1)

    assert call_count == 1, "a permission error must not be retried"


@pytest.mark.parametrize(
    "body",
    [
        '{"status":500,"message":"403 FORBIDDEN"}',
        '{"status":500,"message":"status 403 reading Zuul#call()"}',
        '{"status":500,"message":"403"}',
        "{\"status\":500,\"message\":\"'403'\"}",
    ],
    ids=["forbidden-word", "status-403", "quoted-403", "single-quoted-403"],
)
def test_wrapped_403_body_variants_raise_auth_error(mock_router, client, body):
    mock_router.get("/dataflow/v1/1").mock(return_value=httpx.Response(500, text=body))
    with pytest.raises(AuthError):
        client.get_dataflow(dataflow_id=1)


def test_genuine_500_still_raises_api_error_and_is_retried(client):
    """A server error with no auth marker must keep its old behaviour."""
    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, text='{"status":500,"message":"COMMAND_EXCEPTION"}')

    with patch.object(client._http._client, "request", side_effect=mock_request):
        with _patch_sleep(), _patch_random():
            with pytest.raises(APIError) as exc_info:
                client.get_dataflow(dataflow_id=1)

    assert not isinstance(exc_info.value, AuthError)
    # _MAX_RETRIES=3 retries, so 4 calls in total.
    assert call_count == 4, "genuine 5xx on GET should still retry"


# ── ping() and reporter-scoped keys ───────────────────────────────────────────
# A Lead Reporter key is 403'd on /dataflow/v1/{id} while being perfectly valid
# for the endpoints it owns. Reporting it as revoked is wrong and sends users
# chasing a credential problem that doesn't exist. Verified live on 2003.

def test_ping_true_when_403_on_dataflow_but_representatives_readable(mock_router, client):
    mock_router.get("/dataflow/v1/1").mock(return_value=httpx.Response(403, text="Forbidden"))
    mock_router.get("/representative/v1/dataflow/1").mock(return_value=httpx.Response(200, json=[]))
    assert client.ping(dataflow_id=1) is True


def test_ping_false_when_both_probes_are_forbidden(mock_router, client):
    mock_router.get("/dataflow/v1/1").mock(return_value=httpx.Response(403, text="Forbidden"))
    mock_router.get("/representative/v1/dataflow/1").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    assert client.ping(dataflow_id=1) is False


def test_ping_false_on_401_without_a_second_probe(mock_router, client):
    """A bad key is bad everywhere — don't waste a request confirming it."""
    mock_router.get("/dataflow/v1/1").mock(return_value=httpx.Response(401, text="Unauthorized"))
    route = mock_router.get("/representative/v1/dataflow/1").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert client.ping(dataflow_id=1) is False
    assert route.call_count == 0
