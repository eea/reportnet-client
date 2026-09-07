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
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": False})
    )
    route = mock_router.post("/dataset/v2/importFileData/10").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    df_client.import_file(dataset_id=10, file=b"data")
    assert "dataflowId=5" in str(route.calls[0].request.url)


def test_import_file_uses_default_provider_id(mock_router, df_client):
    """Citus (non-BigData) dataflows still auto-fill the stored provider_id."""
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": False})
    )
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


def test_import_file_bigdata_does_not_auto_fill_provider_id(mock_router, df_client):
    """BigData rejects providerId with a 403, so the stored default must not
    be auto-injected — only an explicit override is forwarded."""
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    route = mock_router.post("/dataset/v2/importFileData/10").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    df_client.import_file(dataset_id=10, file=b"data")
    assert "providerId" not in str(route.calls[0].request.url)


def test_import_file_bigdata_forwards_explicit_provider_id_override(mock_router, df_client):
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    route = mock_router.post("/dataset/v2/importFileData/10").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    df_client.import_file(dataset_id=10, file=b"data", provider_id=99)
    assert "providerId=99" in str(route.calls[0].request.url)


def test_etl_export_prefills_dataflow_id(mock_router, df_client):
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    route = mock_router.get("/dataset/v4/etlExport/10").mock(
        return_value=httpx.Response(200, json={"pollingUrl": POLLING_URL, "status": "QUEUED"})
    )
    handle = df_client.etl_export(dataset_id=10)
    assert isinstance(handle, JobHandle)
    assert "dataflowId=5" in str(route.calls[0].request.url)


def test_etl_export_sends_provider_id_for_reporter_keys(mock_router, df_client):
    """Reporter keys MUST send providerId to export — verified live: without it
    the API 403s, with it the export is accepted. This previously asserted the
    opposite, which made exports impossible for reporters."""
    mock_router.get("/dataflow/v1/5").mock(return_value=httpx.Response(403, text="Forbidden"))
    mock_router.get("/representative/v1/dataflow/5").mock(
        return_value=httpx.Response(200, json=[])
    )
    route = mock_router.get("/dataset/v4/etlExport/10").mock(
        return_value=httpx.Response(200, json={"pollingUrl": POLLING_URL, "status": "QUEUED"})
    )
    df_client.etl_export(dataset_id=10, version=4)
    assert route.calls[0].request.url.params["providerId"] == "42"


def test_etl_export_omits_provider_id_for_custodian_keys_on_bigdata(mock_router, df_client):
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    route = mock_router.get("/dataset/v4/etlExport/10").mock(
        return_value=httpx.Response(200, json={"pollingUrl": POLLING_URL, "status": "QUEUED"})
    )
    df_client.etl_export(dataset_id=10, version=4)
    assert "providerId" not in route.calls[0].request.url.params


def test_etl_export_retries_with_the_opposite_provider_id_on_403(mock_router, df_client):
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    route = mock_router.get("/dataset/v4/etlExport/10")
    route.side_effect = [
        httpx.Response(403, text="Forbidden"),
        httpx.Response(200, json={"pollingUrl": POLLING_URL, "status": "QUEUED"}),
    ]
    df_client.etl_export(dataset_id=10, version=4)
    assert route.call_count == 2
    assert "providerId" not in route.calls[0].request.url.params
    assert route.calls[1].request.url.params["providerId"] == "42"


def test_etl_export_v4_forwards_explicit_provider_id_override(mock_router, df_client):
    route = mock_router.get("/dataset/v4/etlExport/10").mock(
        return_value=httpx.Response(200, json={"pollingUrl": POLLING_URL, "status": "QUEUED"})
    )
    df_client.etl_export(dataset_id=10, version=4, provider_id=99)
    assert "providerId=99" in str(route.calls[0].request.url)


def test_etl_export_uses_v3_for_citus(mock_router, df_client):
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": False})
    )
    route = mock_router.get("/dataset/v3/etlExport/10").mock(
        return_value=httpx.Response(200, json={"pollingUrl": POLLING_URL, "status": "QUEUED"})
    )
    handle = df_client.etl_export(dataset_id=10)
    assert isinstance(handle, JobHandle)
    assert "dataflowId=5" in str(route.calls[0].request.url)


def test_etl_export_explicit_version_skips_detection(mock_router, df_client):
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    route = mock_router.get("/dataset/v4/etlExport/10").mock(
        return_value=httpx.Response(200, json={"pollingUrl": POLLING_URL, "status": "QUEUED"})
    )
    handle = df_client.etl_export(dataset_id=10, version=4)
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
