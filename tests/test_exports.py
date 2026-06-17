from unittest.mock import patch

import httpx
import pytest

from reportnet import JobHandle
from reportnet.models import JobHandle as JobHandleModel

POLLING_URL  = "/orchestrator/jobs/pollForJobStatus/200?datasetId=1&dataflowId=2"
DOWNLOAD_URL = "/orchestrator/jobs/downloadEtlExportedFile/200?datasetId=1&dataflowId=2"
EXPORT_RESPONSE = {"pollingUrl": POLLING_URL, "status": "QUEUED"}


def test_etl_export_returns_handle(mock_router, client):
    mock_router.get("/dataset/v4/etlExport/1").mock(
        return_value=httpx.Response(200, json=EXPORT_RESPONSE)
    )
    handle = client.etl_export(dataset_id=1, dataflow_id=2)
    assert isinstance(handle, JobHandle)
    assert handle.job_id == 200
    assert handle._is_export is True
    assert handle._download_url is None  # not known until FINISHED


def test_etl_export_job_id_from_response(mock_router, client):
    mock_router.get("/dataset/v4/etlExport/1").mock(
        return_value=httpx.Response(200, json={"jobId": 999, "pollingUrl": POLLING_URL, "status": "QUEUED"})
    )
    handle = client.etl_export(dataset_id=1, dataflow_id=2)
    assert handle.job_id == 999


def test_result_waits_and_downloads(mock_router, client):
    mock_router.get("/dataset/v4/etlExport/1").mock(
        return_value=httpx.Response(200, json=EXPORT_RESPONSE)
    )
    mock_router.get("/orchestrator/jobs/pollForJobStatus/200").mock(
        side_effect=[
            httpx.Response(200, json={"status": "IN_PROGRESS"}),
            httpx.Response(200, json={"status": "FINISHED", "downloadUrl": DOWNLOAD_URL}),
        ]
    )
    mock_router.get("/orchestrator/jobs/downloadEtlExportedFile/200").mock(
        return_value=httpx.Response(200, content=b"PK\x03\x04zipdata")
    )
    handle = client.etl_export(dataset_id=1, dataflow_id=2)
    with patch("time.sleep"):
        data = handle.result(poll_interval=0)
    assert data == b"PK\x03\x04zipdata"
    assert handle._download_url == DOWNLOAD_URL


def test_export_file_returns_bytes(mock_router, client):
    mock_router.post("/dataset/exportFile").mock(
        return_value=httpx.Response(200, content=b"col1,col2\nval1,val2")
    )
    result = client.export_file(dataset_id=1, table_schema_id="abc", mime_type="csv")
    assert result == b"col1,col2\nval1,val2"


def test_export_file_dl_returns_bytes(mock_router, client):
    mock_router.post("/dataset/exportFileDL").mock(
        return_value=httpx.Response(200, content=b"csv data")
    )
    result = client.export_file_dl(dataset_id=1, table_schema_id="abc")
    assert result == b"csv data"


def test_result_raises_on_non_export_handle(mock_router, client):
    handle = JobHandleModel(job_id=1, polling_url=POLLING_URL, _http=client._http)
    with pytest.raises(TypeError, match="etl_export"):
        handle.result()


def test_download_validation_snapshot(mock_router, client):
    mock_router.get("/downloadValidation/42").mock(
        return_value=httpx.Response(200, content=b"rule,count\nerror,5")
    )
    result = client.download_validation_snapshot(
        snapshot_id=42, dataset_id=1, dataflow_id=2, provider_id=17
    )
    assert result == b"rule,count\nerror,5"
