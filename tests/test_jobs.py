from unittest.mock import patch

import httpx
import pytest

from reportnet import JobStatus
from reportnet.exceptions import JobFailedError, JobTimeoutError
from reportnet.models import JobHandle

POLLING_URL = "/orchestrator/jobs/pollForJobStatus/1?datasetId=1&dataflowId=2"


def _handle(client):
    return JobHandle(job_id=1, polling_url=POLLING_URL, _http=client._http)


def test_status_finished(mock_router, client):
    mock_router.get("/orchestrator/jobs/pollForJobStatus/1").mock(
        return_value=httpx.Response(200, json={"status": "FINISHED"})
    )
    assert _handle(client).status() == JobStatus.FINISHED


def test_wait_polls_until_finished(mock_router, client):
    mock_router.get("/orchestrator/jobs/pollForJobStatus/1").mock(
        side_effect=[
            httpx.Response(200, json={"status": "QUEUED"}),
            httpx.Response(200, json={"status": "IN_PROGRESS"}),
            httpx.Response(200, json={"status": "FINISHED"}),
        ]
    )
    handle = _handle(client)
    with patch("time.sleep"):
        result = handle.wait(poll_interval=0)
    assert result is handle


def test_wait_raises_job_failed(mock_router, client):
    mock_router.get("/orchestrator/jobs/pollForJobStatus/1").mock(
        return_value=httpx.Response(200, json={"status": "FAILED"})
    )
    with pytest.raises(JobFailedError) as exc_info:
        _handle(client).wait()
    assert exc_info.value.job_id == 1
    assert exc_info.value.status == "FAILED"


def test_wait_raises_on_canceled(mock_router, client):
    mock_router.get("/orchestrator/jobs/pollForJobStatus/1").mock(
        return_value=httpx.Response(200, json={"status": "CANCELED_BY_ADMIN"})
    )
    with pytest.raises(JobFailedError):
        _handle(client).wait()


def test_wait_raises_timeout(mock_router, client):
    mock_router.get("/orchestrator/jobs/pollForJobStatus/1").mock(
        return_value=httpx.Response(200, json={"status": "IN_PROGRESS"})
    )
    with patch("time.sleep"), pytest.raises(JobTimeoutError) as exc_info:
        _handle(client).wait(poll_interval=0, timeout=0.001)
    assert exc_info.value.job_id == 1


@pytest.mark.parametrize(
    "status, expected",
    [
        (JobStatus.QUEUED, False),
        (JobStatus.IN_PROGRESS, False),
        (JobStatus.FINISHED, True),
        (JobStatus.FAILED, True),
        (JobStatus.CANCELED, True),
        (JobStatus.REFUSED, True),
        (JobStatus.CANCELED_BY_ADMIN, True),
    ],
)
def test_is_terminal(status, expected):
    assert status.is_terminal == expected


def test_is_successful_only_finished():
    assert JobStatus.FINISHED.is_successful
    assert not JobStatus.FAILED.is_successful
    assert not JobStatus.CANCELED.is_successful
