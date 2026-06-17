import httpx
import pytest

from reportnet import JobHandle

POLLING_URL = "/orchestrator/jobs/pollForJobStatus/200?datasetId=1&dataflowId=2"
EXPORT_RESPONSE = {"pollingUrl": POLLING_URL, "status": "QUEUED"}


def test_etl_export_returns_handle(mock_router, client):
    mock_router.get("/dataset/v4/etlExport/1").mock(
        return_value=httpx.Response(200, json=EXPORT_RESPONSE)
    )
    handle = client.etl_export(dataset_id=1, dataflow_id=2)
    assert isinstance(handle, JobHandle)
    assert handle.job_id == 200
    assert handle._download_path == "/orchestrator/jobs/download/200"


def test_etl_export_job_id_from_response(mock_router, client):
    # When the API includes jobId directly in the response body
    mock_router.get("/dataset/v4/etlExport/1").mock(
        return_value=httpx.Response(200, json={"jobId": 999, "pollingUrl": POLLING_URL, "status": "QUEUED"})
    )
    handle = client.etl_export(dataset_id=1, dataflow_id=2)
    assert handle.job_id == 999


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
    from reportnet.models import JobHandle

    handle = JobHandle(job_id=1, polling_url=POLLING_URL, _http=client._http)
    with pytest.raises(TypeError, match="etl_export"):
        handle.result()
