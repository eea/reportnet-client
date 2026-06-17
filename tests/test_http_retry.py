"""Tests for retry / back-off logic in HttpSession._request."""
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from reportnet import JobHandle, ReportnetClient
from reportnet.exceptions import APIError, RateLimitError

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
