"""Tests for dataflow-level metadata and new dataset management methods."""
import httpx

from reportnet import DataflowInfo, Reporter
from reportnet.dataflow import DataflowClient

DATAFLOW_RESPONSE = {
    "id": 1619,
    "name": "EU GHG Inventory",
    "description": "Greenhouse gas inventory reporting",
    "type": "REPORTING",
    "status": "PUBLIC",
}

REPORTERS_RESPONSE = [
    {"id": 10, "dataflowId": 1619, "dataProviderId": 42, "datasetId": 93953},
    {"id": 11, "dataflowId": 1619, "dataProviderId": 43, "datasetId": None},
]


# ── DataflowInfo ──────────────────────────────────────────────────────────────

def test_get_dataflow_returns_info(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    info = client.get_dataflow(dataflow_id=1619)
    assert isinstance(info, DataflowInfo)
    assert info.id == 1619
    assert info.name == "EU GHG Inventory"
    assert info.type == "REPORTING"
    assert info.status == "PUBLIC"


def test_dataflow_client_get_dataflow(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    df = client.for_dataflow(1619)
    info = df.get_dataflow()
    assert info.id == 1619


# ── Reporters ─────────────────────────────────────────────────────────────────

def test_get_reporters_returns_list(mock_router, client):
    mock_router.get("/representative/v1/dataflow/1619").mock(
        return_value=httpx.Response(200, json=REPORTERS_RESPONSE)
    )
    reporters = client.get_reporters(dataflow_id=1619)
    assert len(reporters) == 2
    assert isinstance(reporters[0], Reporter)
    assert reporters[0].provider_id == 42
    assert reporters[0].dataset_id == 93953
    assert reporters[1].dataset_id is None


def test_dataflow_client_get_reporters(mock_router, client):
    mock_router.get("/representative/v1/dataflow/1619").mock(
        return_value=httpx.Response(200, json=REPORTERS_RESPONSE)
    )
    reporters = client.for_dataflow(1619).get_reporters()
    assert reporters[0].dataflow_id == 1619


# ── is_big_dataflow ───────────────────────────────────────────────────────────

def test_is_big_dataflow_true(mock_router, client):
    mock_router.get("/dataflow/private/v1/1619/isBigDataflow").mock(
        return_value=httpx.Response(200, json=True)
    )
    assert client.is_big_dataflow(dataflow_id=1619) is True


def test_is_big_dataflow_false(mock_router, client):
    mock_router.get("/dataflow/private/v1/1619/isBigDataflow").mock(
        return_value=httpx.Response(200, json=False)
    )
    assert client.for_dataflow(1619).is_big_dataflow() is False


# ── for_provider ──────────────────────────────────────────────────────────────

def test_for_provider_creates_scoped_client(client):
    df = client.for_dataflow(1619)
    ie = df.for_provider(42)
    assert isinstance(ie, DataflowClient)
    assert ie._dataflow_id == 1619
    assert ie._provider_id == 42


def test_for_provider_injects_provider_id(mock_router, client):
    route = mock_router.put("/orchestrator/jobs/addValidationJob/93953").mock(
        return_value=httpx.Response(200, json=99)
    )
    mock_router.get("/orchestrator/jobs/pollForJobStatus/99").mock(
        return_value=httpx.Response(200, json={"status": "FINISHED"})
    )
    ie = client.for_dataflow(1619).for_provider(42)
    ie.add_validation_job(dataset_id=93953)
    assert "providerId=42" in str(route.calls[0].request.url)


# ── delete_dataset_data ───────────────────────────────────────────────────────

def test_delete_dataset_data(mock_router, client):
    route = mock_router.delete("/dataset/v1/1/deleteDatasetData").mock(
        return_value=httpx.Response(200)
    )
    client.delete_dataset_data(dataset_id=1, dataflow_id=2)
    assert route.called
    assert "dataflowId=2" in str(route.calls[0].request.url)


def test_delete_dataset_data_with_provider(mock_router, client):
    route = mock_router.delete("/dataset/v1/1/deleteDatasetData").mock(
        return_value=httpx.Response(200)
    )
    client.delete_dataset_data(dataset_id=1, dataflow_id=2, provider_id=42)
    assert "providerId=42" in str(route.calls[0].request.url)


def test_dataflow_client_delete_dataset_data(mock_router, client):
    route = mock_router.delete("/dataset/v1/93953/deleteDatasetData").mock(
        return_value=httpx.Response(200)
    )
    client.for_dataflow(1619).for_provider(42).delete_dataset_data(dataset_id=93953)
    assert "providerId=42" in str(route.calls[0].request.url)
    assert "dataflowId=1619" in str(route.calls[0].request.url)


# ── delete_table_data ─────────────────────────────────────────────────────────

def test_delete_table_data(mock_router, client):
    route = mock_router.delete("/dataset/v1/1/deleteTableData/schema-abc").mock(
        return_value=httpx.Response(200)
    )
    client.delete_table_data(dataset_id=1, table_schema_id="schema-abc", dataflow_id=2)
    assert route.called


# ── list_historic_releases ────────────────────────────────────────────────────

def test_list_historic_releases(mock_router, client):
    releases = [{"id": 1, "datasetId": 93953, "releaseDate": "2024-01-01"}]
    mock_router.get("/snapshot/v1/historicReleases").mock(
        return_value=httpx.Response(200, json=releases)
    )
    result = client.list_historic_releases(dataset_id=93953, dataflow_id=1619)
    assert result == releases


def test_dataflow_client_list_historic_releases(mock_router, client):
    mock_router.get("/snapshot/v1/historicReleases").mock(
        return_value=httpx.Response(200, json=[])
    )
    result = client.for_dataflow(1619).list_historic_releases(dataset_id=93953)
    assert result == []


# ── check_import_process ──────────────────────────────────────────────────────

def test_check_import_process(mock_router, client):
    lock_response = {"anyLockAssigned": True, "importInProgress": True}
    mock_router.get("/dataset/checkImportProcess/1").mock(
        return_value=httpx.Response(200, json=lock_response)
    )
    result = client.check_import_process(dataset_id=1)
    assert result["importInProgress"] is True
