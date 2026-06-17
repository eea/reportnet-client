import io
import zipfile
from unittest.mock import patch

import httpx
import pytest

from reportnet import JobHandle
from reportnet.models import JobHandle as JobHandleModel


def _make_zip(*csv_pairs: tuple[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in csv_pairs:
            zf.writestr(name, data)
    return buf.getvalue()

POLLING_URL  = "/orchestrator/jobs/pollForJobStatus/200?datasetId=1&dataflowId=2"
DOWNLOAD_URL = "/orchestrator/jobs/downloadEtlExportedFile/200?datasetId=1&dataflowId=2"
EXPORT_RESPONSE = {"pollingUrl": POLLING_URL, "status": "QUEUED"}
JOB_RESPONSE = {"jobId": 200, "pollingUrl": POLLING_URL}


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
        return_value=httpx.Response(
            200, json={"jobId": 999, "pollingUrl": POLLING_URL, "status": "QUEUED"}
        )
    )
    handle = client.etl_export(dataset_id=1, dataflow_id=2)
    assert handle.job_id == 999


def test_etl_export_v5(mock_router, client):
    route = mock_router.get("/dataset/v5/etlExport/1").mock(
        return_value=httpx.Response(200, json=EXPORT_RESPONSE)
    )
    handle = client.etl_export(dataset_id=1, dataflow_id=2, version=5)
    assert handle.job_id == 200
    assert route.called


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


def test_export_file_returns_handle(mock_router, client):
    mock_router.post("/dataset/exportFile").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    handle = client.export_file(dataset_id=1, table_schema_id="abc", mime_type="csv")
    assert isinstance(handle, JobHandle)
    assert handle._is_export is True
    assert handle.job_id == 200


def test_export_file_dl_returns_handle(mock_router, client):
    mock_router.post("/dataset/exportFileDL").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    handle = client.export_file_dl(dataset_id=1, table_schema_id="abc")
    assert isinstance(handle, JobHandle)
    assert handle._is_export is True
    assert handle.job_id == 200


def test_export_dataset_file_returns_handle(mock_router, client):
    mock_router.get("/dataset/exportDatasetFile").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    handle = client.export_dataset_file(dataset_id=1, mime_type="zip")
    assert isinstance(handle, JobHandle)
    assert handle._is_export is True
    assert handle.job_id == 200


def test_export_dataset_file_dl_returns_handle(mock_router, client):
    mock_router.get("/dataset/exportDatasetFileDL").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    handle = client.export_dataset_file_dl(dataset_id=1)
    assert isinstance(handle, JobHandle)
    assert handle._is_export is True
    assert handle.job_id == 200


def test_to_frames_returns_dict_of_dataframes(mock_router, client):
    pytest.importorskip("polars")
    zip_bytes = _make_zip(
        ("Emissions.csv", b"country,value\nIE,1.2\nDE,3.4"),
        ("Sites.csv", b"id,name\n1,Site A"),
    )
    mock_router.get("/dataset/v4/etlExport/1").mock(
        return_value=httpx.Response(200, json=EXPORT_RESPONSE)
    )
    mock_router.get("/orchestrator/jobs/pollForJobStatus/200").mock(
        return_value=httpx.Response(200, json={"status": "FINISHED", "downloadUrl": DOWNLOAD_URL})
    )
    mock_router.get("/orchestrator/jobs/downloadEtlExportedFile/200").mock(
        return_value=httpx.Response(200, content=zip_bytes)
    )
    handle = client.etl_export(dataset_id=1, dataflow_id=2)
    with patch("time.sleep"):
        frames = handle.to_frames(poll_interval=0)
    assert set(frames) == {"Emissions", "Sites"}
    assert frames["Emissions"].shape == (2, 2)
    assert frames["Sites"].shape == (1, 2)


def test_to_frames_strips_path_prefix(mock_router, client):
    pytest.importorskip("polars")
    zip_bytes = _make_zip(("dataset_1/MyTable.csv", b"a,b\n1,2"))
    mock_router.get("/dataset/v4/etlExport/1").mock(
        return_value=httpx.Response(200, json=EXPORT_RESPONSE)
    )
    mock_router.get("/orchestrator/jobs/pollForJobStatus/200").mock(
        return_value=httpx.Response(200, json={"status": "FINISHED", "downloadUrl": DOWNLOAD_URL})
    )
    mock_router.get("/orchestrator/jobs/downloadEtlExportedFile/200").mock(
        return_value=httpx.Response(200, content=zip_bytes)
    )
    handle = client.etl_export(dataset_id=1, dataflow_id=2)
    with patch("time.sleep"):
        frames = handle.to_frames(poll_interval=0)
    assert list(frames) == ["MyTable"]


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
