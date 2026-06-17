import httpx
import pytest

from reportnet import DataflowClient, JobHandle

POLLING_URL = "/orchestrator/jobs/pollForJobStatus/1?datasetId=10&dataflowId=5"
JOB_RESPONSE = {"jobId": 1, "pollingUrl": POLLING_URL}
VALIDATION_RESULTS = {"validations": []}


@pytest.fixture
def df_client(mock_router, client):
    return client.for_dataflow(dataflow_id=5, provider_id=42)


def test_for_dataflow_returns_dataflow_client(client):
    dc = client.for_dataflow(dataflow_id=5)
    assert isinstance(dc, DataflowClient)
    assert dc._dataflow_id == 5
    assert dc._provider_id is None


def test_for_dataflow_stores_provider_id(client):
    dc = client.for_dataflow(dataflow_id=5, provider_id=42)
    assert dc._provider_id == 42


def test_import_file_prefills_dataflow_id(mock_router, df_client):
    route = mock_router.post("/dataset/v2/importFileData/10").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    df_client.import_file(dataset_id=10, file=b"data")
    assert "dataflowId=5" in str(route.calls[0].request.url)


def test_import_file_uses_default_provider_id(mock_router, df_client):
    route = mock_router.post("/dataset/v2/importFileData/10").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    df_client.import_file(dataset_id=10, file=b"data")
    assert "providerId=42" in str(route.calls[0].request.url)


def test_import_file_overrides_provider_id(mock_router, df_client):
    route = mock_router.post("/dataset/v2/importFileData/10").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    df_client.import_file(dataset_id=10, file=b"data", provider_id=99)
    assert "providerId=99" in str(route.calls[0].request.url)


def test_etl_export_prefills_dataflow_id(mock_router, df_client):
    route = mock_router.get("/dataset/v4/etlExport/10").mock(
        return_value=httpx.Response(200, json={"pollingUrl": POLLING_URL, "status": "QUEUED"})
    )
    handle = df_client.etl_export(dataset_id=10)
    assert isinstance(handle, JobHandle)
    assert "dataflowId=5" in str(route.calls[0].request.url)


def test_add_validation_job_prefills_dataflow_id(mock_router, df_client):
    route = mock_router.put("/orchestrator/jobs/addValidationJob/10").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    df_client.add_validation_job(dataset_id=10)
    assert "dataflowId=5" in str(route.calls[0].request.url)
    assert "providerId=42" in str(route.calls[0].request.url)


def test_list_group_validations_prefills_dataflow_id(mock_router, df_client):
    mock_router.get("/validation/listGroupValidations/10").mock(
        return_value=httpx.Response(200, json=VALIDATION_RESULTS)
    )
    result = df_client.list_group_validations(dataset_id=10)
    assert result == VALIDATION_RESULTS


def test_download_validation_snapshot_uses_stored_provider_id(mock_router, df_client):
    route = mock_router.get("/downloadValidation/7").mock(
        return_value=httpx.Response(200, content=b"csv")
    )
    df_client.download_validation_snapshot(snapshot_id=7, dataset_id=10)
    assert "providerId=42" in str(route.calls[0].request.url)


def test_download_validation_snapshot_raises_without_provider_id(client):
    dc = client.for_dataflow(dataflow_id=5)  # no provider_id
    with pytest.raises(ValueError, match="provider_id"):
        dc.download_validation_snapshot(snapshot_id=7, dataset_id=10)


def test_set_reference_dataset_updatable(mock_router, df_client):
    route = mock_router.put("/referenceDataset/10").mock(
        return_value=httpx.Response(200)
    )
    df_client.set_reference_dataset_updatable(dataset_id=10, updatable=True)
    assert "dataflowId=5" in str(route.calls[0].request.url)
