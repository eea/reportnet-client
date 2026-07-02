"""Tests for dataflow-level metadata and new dataset management methods."""
import httpx

from reportnet import DataflowInfo, ReferenceDataset, Reporter, ReportingDataset, TestDataset
from reportnet.dataflow import DataflowClient

DATAFLOW_RESPONSE = {
    "id": 1619,
    "name": "EU GHG Inventory",
    "description": "Greenhouse gas inventory reporting",
    "type": "REPORTING",
    "status": "PUBLIC",
    "reportingDatasets": [
        {
            "id": 93954,
            "dataSetName": "France",
            "dataProviderId": 56,
            "datasetSchema": "schema-abc",
            "nameDatasetSchema": "Table1a",
            "status": "PENDING",
        },
        {
            "id": 93958,
            "dataSetName": "France",
            "dataProviderId": 56,
            "datasetSchema": "schema-def",
            "nameDatasetSchema": "Table7",
            "status": "PENDING",
        },
        {
            "id": 93977,
            "dataSetName": "Italy",
            "dataProviderId": 64,
            "datasetSchema": "schema-abc",
            "nameDatasetSchema": "Table1a",
            "status": "PENDING",
        },
    ],
    "referenceDatasets": [
        {
            "id": 93975,
            "dataSetName": "Reference Dataset - Codelist",
            "creationDate": 1759385530194,
            "status": None,
            "datasetSchema": "schema-ref",
            "idDataflow": None,
            "publicFileName": "Reference Dataset - Codelist.zip",
            "updatable": False,
        },
    ],
    "testDatasets": [
        {
            "id": 93953,
            "dataSetName": "Test Dataset - Table1a",
            "creationDate": 1759385530194,
            "status": None,
            "datasetSchema": "schema-abc",
            "idDataflow": None,
        },
        {
            "id": 93957,
            "dataSetName": "Test Dataset - Table7",
            "creationDate": 1759385530194,
            "status": None,
            "datasetSchema": "schema-def",
            "idDataflow": None,
        },
    ],
}

REPORTERS_RESPONSE = [
    # The API does not echo dataflowId in the representatives list response;
    # client.get_reporters() injects it from the URL parameter.
    {"id": 10, "dataProviderId": 42},
    {"id": 11, "dataProviderId": 43},
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


def test_get_reporters_injects_dataflow_id(mock_router, client):
    mock_router.get("/representative/v1/dataflow/1619").mock(
        return_value=httpx.Response(200, json=REPORTERS_RESPONSE)
    )
    reporters = client.get_reporters(dataflow_id=1619)
    # dataflowId is not in the API response — must be injected from the URL param
    assert reporters[0].dataflow_id == 1619
    assert reporters[1].dataflow_id == 1619


def test_dataflow_client_get_reporters(mock_router, client):
    mock_router.get("/representative/v1/dataflow/1619").mock(
        return_value=httpx.Response(200, json=REPORTERS_RESPONSE)
    )
    reporters = client.for_dataflow(1619).get_reporters()
    assert reporters[0].dataflow_id == 1619


def test_reporter_country_code(mock_router, client):
    mock_router.get("/representative/v1/dataflow/1619").mock(
        return_value=httpx.Response(200, json=REPORTERS_RESPONSE)
    )
    reporters = client.get_reporters(dataflow_id=1619)
    # provider_id=42 is Austria (AT) in the providers mapping
    r = reporters[0]
    assert r.country_code is not None   # in mapping
    assert len(r.country_code) == 2     # two-letter ISO code
    assert r.country_name is not None

    # provider_id=43 — just verify property doesn't raise for any id
    r2 = reporters[1]
    _ = r2.country_code   # None is fine if not in mapping


# ── get_reporting_datasets ────────────────────────────────────────────────────

def test_get_reporting_datasets(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    datasets = client.get_reporting_datasets(dataflow_id=1619)
    assert len(datasets) == 3
    assert isinstance(datasets[0], ReportingDataset)
    assert datasets[0].id == 93954
    assert datasets[0].provider_id == 56
    assert datasets[0].table_name == "Table1a"
    assert datasets[0].status == "PENDING"


def test_get_reporting_datasets_filtered_by_provider(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    all_ds = client.for_dataflow(1619).get_reporting_datasets()
    france = [ds for ds in all_ds if ds.provider_id == 56]
    assert len(france) == 2
    assert {ds.table_name for ds in france} == {"Table1a", "Table7"}


def test_scoped_client_get_reporting_datasets_filters_automatically(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    france = client.for_dataflow(1619).for_provider(56).get_reporting_datasets()
    assert len(france) == 2
    assert all(ds.provider_id == 56 for ds in france)

    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    italy = client.for_dataflow(1619).for_provider(64).get_reporting_datasets()
    assert len(italy) == 1
    assert italy[0].table_name == "Table1a"


def test_reporting_dataset_no_datasets_key(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json={"id": 1619, "name": "x", "status": "DRAFT",
                                               "description": "", "type": "REPORTING"})
    )
    datasets = client.get_reporting_datasets(dataflow_id=1619)
    assert datasets == []


# ── get_reference_datasets ────────────────────────────────────────────────────

def test_get_reference_datasets(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    refs = client.get_reference_datasets(dataflow_id=1619)
    assert len(refs) == 1
    assert isinstance(refs[0], ReferenceDataset)
    assert refs[0].id == 93975
    assert refs[0].name == "Reference Dataset - Codelist"
    assert refs[0].schema_id == "schema-ref"
    assert refs[0].updatable is False
    assert refs[0].public_filename == "Reference Dataset - Codelist.zip"


def test_get_reference_datasets_empty(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json={"id": 1619, "name": "x", "status": "DRAFT",
                                               "description": "", "type": "REPORTING"})
    )
    assert client.get_reference_datasets(dataflow_id=1619) == []


def test_dataflow_client_get_reference_datasets(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    refs = client.for_dataflow(1619).get_reference_datasets()
    assert refs[0].id == 93975


# ── get_test_datasets ─────────────────────────────────────────────────────────

def test_get_test_datasets(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    tests = client.get_test_datasets(dataflow_id=1619)
    assert len(tests) == 2
    assert isinstance(tests[0], TestDataset)
    assert tests[0].id == 93953
    assert tests[0].name == "Test Dataset - Table1a"
    assert tests[0].schema_id == "schema-abc"


def test_get_test_datasets_empty(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json={"id": 1619, "name": "x", "status": "DRAFT",
                                               "description": "", "type": "REPORTING"})
    )
    assert client.get_test_datasets(dataflow_id=1619) == []


def test_dataflow_client_get_test_datasets(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    tests = client.for_dataflow(1619).get_test_datasets()
    assert {t.schema_id for t in tests} == {"schema-abc", "schema-def"}


# ── is_big_dataflow ───────────────────────────────────────────────────────────

def test_is_big_dataflow_true(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json={**DATAFLOW_RESPONSE, "bigData": True})
    )
    assert client.is_big_dataflow(dataflow_id=1619) is True


def test_is_big_dataflow_false(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json={**DATAFLOW_RESPONSE, "bigData": False})
    )
    assert client.for_dataflow(1619).is_big_dataflow() is False


# ── ping ──────────────────────────────────────────────────────────────────────

def test_ping_returns_true_on_success(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    assert client.ping(dataflow_id=1619) is True


def test_ping_returns_false_on_auth_error(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(401)
    )
    assert client.ping(dataflow_id=1619) is False


def test_dataflow_client_ping(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    assert client.for_dataflow(1619).ping() is True


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


# ── find_reporter ─────────────────────────────────────────────────────────────

# provider_id=42 maps to "AD" (Andorra) in the PROVIDERS table.
_FIND_REPORTER_RESPONSE = [
    {"id": 10, "dataProviderId": 42},   # AD (Andorra)
    {"id": 11, "dataProviderId": 17},   # IE (Ireland)
]


def test_find_reporter_returns_scoped_client(mock_router, client):
    from reportnet.dataflow import DataflowClient

    mock_router.get("/representative/v1/dataflow/1619").mock(
        return_value=httpx.Response(200, json=_FIND_REPORTER_RESPONSE)
    )
    ie = client.for_dataflow(1619).find_reporter("IE")
    assert isinstance(ie, DataflowClient)
    assert ie._provider_id == 17
    assert ie._dataflow_id == 1619


def test_find_reporter_case_insensitive(mock_router, client):
    mock_router.get("/representative/v1/dataflow/1619").mock(
        return_value=httpx.Response(200, json=_FIND_REPORTER_RESPONSE)
    )
    ie = client.for_dataflow(1619).find_reporter("ie")
    assert ie._provider_id == 17


def test_find_reporter_unknown_country_raises(mock_router, client):
    import pytest

    mock_router.get("/representative/v1/dataflow/1619").mock(
        return_value=httpx.Response(200, json=_FIND_REPORTER_RESPONSE)
    )
    with pytest.raises(ValueError, match="XX"):
        client.for_dataflow(1619).find_reporter("XX")


# ── to_mermaid ────────────────────────────────────────────────────────────────
# get_dataflow / get_reference_datasets / get_reporting_datasets / get_test_datasets
# all hit the same GET /dataflow/v1/{id} endpoint, so one mock covers all of them.

def test_to_mermaid_basic_structure(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    mmd = client.for_dataflow(1619).to_mermaid()

    assert mmd.startswith("graph LR")
    assert 'df[["' in mmd                 # dataflow node
    assert "id=1619" in mmd
    assert "ref_93975" in mmd             # reference dataset node
    # One node per provider (France=56, Italy=64), not per reporting dataset
    assert "p_56" in mmd
    assert "p_64" in mmd
    # Test datasets are excluded unless include_test=True
    assert "test_93953" not in mmd
    assert "test_93957" not in mmd


def test_to_mermaid_include_test(mock_router, client):
    mock_router.get("/dataflow/v1/1619").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    mmd = client.for_dataflow(1619).to_mermaid(include_test=True)

    assert "test_93953" in mmd
    assert "test_93957" in mmd


def test_to_mermaid_escapes_html_special_chars(mock_router, client):
    resp = {
        **DATAFLOW_RESPONSE,
        "name": 'A & B <script> "quoted" #tag',
        "reportingDatasets": [],
        "referenceDatasets": [],
        "testDatasets": [],
    }
    mock_router.get("/dataflow/v1/1619").mock(return_value=httpx.Response(200, json=resp))
    mmd = client.for_dataflow(1619).to_mermaid()

    assert "<script>" not in mmd
    assert "&amp;" in mmd
    assert "&lt;script&gt;" in mmd
    assert "&quot;quoted&quot;" in mmd
    assert "#35;tag" in mmd


def test_to_mermaid_colors_provider_node_by_worst_status(mock_router, client):
    resp = {
        "id": 1619, "name": "x", "description": "", "type": "REPORTING", "status": "PUBLIC",
        "reportingDatasets": [
            {"id": 1, "dataSetName": "France", "dataProviderId": 56,
             "datasetSchema": "s1", "nameDatasetSchema": "Table1a", "status": "FINAL"},
            {"id": 2, "dataSetName": "France", "dataProviderId": 56,
             "datasetSchema": "s2", "nameDatasetSchema": "Table7",
             "status": "CORRECTION_REQUESTED"},
        ],
        "referenceDatasets": [],
        "testDatasets": [],
    }
    mock_router.get("/dataflow/v1/1619").mock(return_value=httpx.Response(200, json=resp))
    mmd = client.for_dataflow(1619).to_mermaid()

    # Worst status across France's two tables is CORRECTION_REQUESTED -> orange fill
    assert "style p_56 fill:#FFD580" in mmd
    assert "1/2 FINAL" in mmd
