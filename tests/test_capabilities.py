"""Tests for the capability model and reporter-scoped behaviour.

Reportnet grants permissions per key role and has no endpoint that reports the
role, so the library probes. This matters because the role changes how requests
must be *built*, not just what succeeds — see docs/api-notes.md.
"""
import httpx
import pytest

import reportnet
from reportnet.exceptions import DiscoveryNotPermittedError

DATAFLOW = {"id": 2, "name": "df", "bigData": True, "reportingDatasets": [
    {"id": 100, "dataSetName": "IT", "dataProviderId": 64,
     "datasetSchema": "s", "nameDatasetSchema": "Table1a", "status": "PENDING"}]}


def _custodian(router):
    router.get("/dataflow/v1/2").mock(return_value=httpx.Response(200, json=DATAFLOW))


def _reporter(router):
    """A Reporter key: 403 on the dataflow, readable representatives."""
    router.get("/dataflow/v1/2").mock(return_value=httpx.Response(403, text="Forbidden"))
    router.get("/representative/v1/dataflow/2").mock(return_value=httpx.Response(200, json=[]))


def _revoked(router):
    router.get("/dataflow/v1/2").mock(return_value=httpx.Response(403, text="Forbidden"))
    router.get("/representative/v1/dataflow/2").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )


def test_custodian_key_is_detected(mock_router, client):
    _custodian(mock_router)
    caps = client.for_dataflow(2).capabilities()
    assert caps.role == "custodian"
    assert caps.can_discover_datasets
    assert not caps.wants_provider_id
    assert caps.is_usable


def test_reporter_key_is_detected(mock_router, client):
    _reporter(mock_router)
    caps = client.for_dataflow(2).capabilities()
    assert caps.role == "reporter"
    assert caps.wants_provider_id, "reporter keys must send providerId"
    assert caps.needs_provider_scope, "reporter reads must be provider-scoped"
    assert caps.can_discover_datasets, "reporters can discover, once scoped"
    assert caps.is_usable


def test_unusable_key_is_detected(mock_router, client):
    _revoked(mock_router)
    caps = client.for_dataflow(2).capabilities()
    assert caps.role == "none"
    assert not caps.is_usable


def test_capabilities_are_probed_once_per_client(mock_router, client):
    _reporter(mock_router)
    route = mock_router.get("/representative/v1/dataflow/2")
    flow = client.for_dataflow(2)
    flow.capabilities()
    flow.capabilities()
    client.for_dataflow(2).for_provider(64).capabilities()
    assert route.call_count == 1, "a key's role never changes; probe once"


def test_custodian_probe_costs_one_request(mock_router, client):
    route = mock_router.get("/dataflow/v1/2").mock(
        return_value=httpx.Response(200, json=DATAFLOW)
    )
    client.for_dataflow(2).capabilities()
    assert route.call_count == 1


# ── Discovery gives an actionable error, not a bare 403 ───────────────────────

def test_reporter_discovers_datasets_when_provider_scoped(mock_router, client):
    """Verified live: GET /dataflow/v1/{id}?providerId=N is permitted for a
    reporter key and returns that provider's own datasets."""
    mock_router.get("/dataflow/v1/2").mock(
        side_effect=lambda request, route: (
            httpx.Response(200, json=DATAFLOW)
            if "providerId" in request.url.params
            else httpx.Response(403, text="Forbidden")
        )
    )
    mock_router.get("/representative/v1/dataflow/2").mock(
        return_value=httpx.Response(200, json=[])
    )
    ds = client.for_dataflow(2).for_provider(64).dataset("Table1a")
    assert ds.id == 100


def test_unscoped_discovery_error_tells_the_caller_to_scope(mock_router, client):
    _reporter(mock_router)
    with pytest.raises(DiscoveryNotPermittedError) as excinfo:
        client.for_dataflow(2).get_reference_datasets()
    msg = str(excinfo.value)
    assert "find_reporter" in msg or "for_provider" in msg


def test_discovery_error_is_still_an_auth_error(mock_router, client):
    """Existing `except AuthError` handlers must keep working."""
    _reporter(mock_router)
    with pytest.raises(reportnet.AuthError):
        client.for_dataflow(2).get_reference_datasets()


def test_schema_and_import_still_work_for_reporter_keys(mock_router, client):
    """The reporter path needs only a dataset ID — that must not be blocked."""
    _reporter(mock_router)
    mock_router.get("/dataschema/v1/datasetId/100").mock(
        return_value=httpx.Response(200, json={
            "idDataSetSchema": "s", "nameDatasetSchema": "D", "tableSchemas": []})
    )
    route = mock_router.post("/dataset/v2/importFileData/100").mock(
        return_value=httpx.Response(200, json={"jobId": 7, "pollingUrl": "/p/7"})
    )
    it = client.for_dataflow(2).for_provider(64)

    assert it.get_schema(dataset_id=100).name == "D"
    it.import_file(dataset_id=100, file=b"a|b\n1|2\n")
    assert route.calls[0].request.url.params["providerId"] == "64"


# ── Reporter-usable verification and backend detection ────────────────────────
# Exports are forbidden to reporter keys, so verify_import() reads import
# statistics instead — the only way such a key can confirm data landed.

SCHEMA = {"idDataSetSchema": "s", "nameDatasetSchema": "D", "tableSchemas": [
    {"idTableSchema": "tbl-a", "nameTableSchema": "Reporter",
     "recordSchema": {"fieldSchema": []}},
    {"idTableSchema": "tbl-b", "nameTableSchema": "Contacts",
     "recordSchema": {"fieldSchema": []}}]}


def test_verify_import_reports_rows_per_table_name(mock_router, client):
    _reporter(mock_router)
    mock_router.get("/dataschema/v1/datasetId/100").mock(
        return_value=httpx.Response(200, json=SCHEMA)
    )
    mock_router.get("/dataset/getImportRelatedStatistics/100").mock(
        return_value=httpx.Response(200, json={
            "tbl-a": {"lastImportDate": 1788769100000,
                      "numberOfRecordsImported": 3, "fileExtension": "csv"},
            "tbl-b": {"lastImportDate": None,
                      "numberOfRecordsImported": None, "fileExtension": None}})
    )
    got = client.for_dataflow(2).for_provider(64).verify_import(dataset_id=100)

    assert got["Reporter"]["records"] == 3
    assert got["Reporter"]["file_extension"] == "csv"
    assert got["Reporter"]["last_import"].year == 2026
    assert got["Contacts"]["records"] is None, "never-imported tables report None"
    assert got["Contacts"]["last_import"] is None


def test_is_big_dataflow_falls_back_to_getmetabase_for_reporter_keys(mock_router, client):
    """Reporter keys are 403 on /dataflow/v1/{id} but may read getmetabase,
    which carries the same bigData field."""
    _reporter(mock_router)
    route = mock_router.get("/dataflow/v1/2/getmetabase").mock(
        return_value=httpx.Response(200, json={"id": 2, "name": "df", "bigData": True})
    )
    assert client.for_dataflow(2).is_big_dataflow() is True
    assert route.call_count == 1
