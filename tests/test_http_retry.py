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
            handle = client.etl_export(dataset_id=1, dataflow_id=2)

    assert call_count == 2
    assert isinstance(handle, JobHandle)


def test_get_raises_after_max_retries_on_transport_error(mock_router, client):
    with patch.object(
        client._http._client,
        "request",
        side_effect=httpx.ConnectError("unreachable"),
    ):
        with _patch_sleep(), _patch_random(), pytest.raises(httpx.ConnectError):
            client.etl_export(dataset_id=1, dataflow_id=2)


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
            handle = client.etl_export(dataset_id=1, dataflow_id=2)

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
            client.etl_export(dataset_id=1, dataflow_id=2)

    assert mock_sleep.call_count == 2
