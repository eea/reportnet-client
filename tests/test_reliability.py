"""Tests for the three reliability/ergonomics behaviours:

1. Codelist resolution never degrades silently.
2. The library logs what it is doing.
3. Datasets are reachable by table name, not list position.
"""
import io
import logging
import zipfile

import httpx
import pytest

import reportnet

# ── Fixtures ──────────────────────────────────────────────────────────────────
# A reporting dataset with one LINK field ("category") whose PK ("pk-cat") lives
# in the SECOND reference dataset — mirroring dataflow 2003, where the codelists
# are not in refs[0].

REPORTING_SCHEMA = {
    "idDataSetSchema": "rep", "nameDatasetSchema": "Reporting",
    "tableSchemas": [{
        "idTableSchema": "t1", "nameTableSchema": "Table1a",
        "recordSchema": {"fieldSchema": [
            {"id": "f1", "name": "category", "type": "LINK",
             "referencedField": {"idDatasetSchema": "ref2", "idPk": "pk-cat"}},
            {"id": "f2", "name": "cyear", "type": "NUMBER_INTEGER"},
        ]},
    }],
}

WRONG_REF_SCHEMA = {
    "idDataSetSchema": "ref1", "nameDatasetSchema": "Units",
    "tableSchemas": [{
        "idTableSchema": "tu", "nameTableSchema": "Units",
        "recordSchema": {"fieldSchema": [{"id": "pk-unit", "name": "unit", "type": "TEXT"}]},
    }],
}

RIGHT_REF_SCHEMA = {
    "idDataSetSchema": "ref2", "nameDatasetSchema": "Categories",
    "tableSchemas": [{
        "idTableSchema": "tc", "nameTableSchema": "Categories",
        "recordSchema": {"fieldSchema": [{"id": "pk-cat", "name": "code", "type": "TEXT"}]},
    }],
}

DATAFLOW_RESPONSE = {
    "id": 5, "name": "Test flow", "bigData": True,
    "reportingDatasets": [
        {"id": 100, "dataSetName": "Ireland", "dataProviderId": 17,
         "datasetSchema": "rep", "nameDatasetSchema": "Table1a", "status": "PENDING"},
        {"id": 101, "dataSetName": "Ireland", "dataProviderId": 17,
         "datasetSchema": "rep2", "nameDatasetSchema": "Table7", "status": "FINAL"},
        {"id": 102, "dataSetName": "Italy", "dataProviderId": 64,
         "datasetSchema": "rep", "nameDatasetSchema": "Table1a", "status": "PENDING"},
    ],
    # Deliberately NOT first: the correct reference dataset is second.
    "referenceDatasets": [
        {"id": 900, "dataSetName": "Reference Dataset - Units", "datasetSchema": "ref1"},
        {"id": 901, "dataSetName": "Reference Dataset - Codelist", "datasetSchema": "ref2"},
    ],
    "testDatasets": [],
}

POLLING_URL = "/orchestrator/jobs/pollForJobStatus/7?datasetId=901&dataflowId=5"
DOWNLOAD_URL = "/orchestrator/jobs/downloadEtlExportedFile/7"


def _csv_zip(name: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, data)
    return buf.getvalue()


def _mock_reference_export(router, dataset_id: int, csv_name: str, csv: bytes) -> None:
    """Wire up the full async export dance for a reference dataset."""
    router.get(f"/dataset/v4/etlExport/{dataset_id}").mock(
        return_value=httpx.Response(200, json={"jobId": 7, "pollingUrl": POLLING_URL})
    )
    router.get(POLLING_URL).mock(
        return_value=httpx.Response(200, json={"status": "FINISHED", "downloadUrl": DOWNLOAD_URL})
    )
    router.get(DOWNLOAD_URL).mock(
        return_value=httpx.Response(200, content=_csv_zip(csv_name, csv))
    )


@pytest.fixture
def flow(mock_router, client):
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json=DATAFLOW_RESPONSE)
    )
    mock_router.get("/dataschema/v1/datasetId/100").mock(
        return_value=httpx.Response(200, json=REPORTING_SCHEMA)
    )
    mock_router.get("/dataschema/v1/datasetId/900").mock(
        return_value=httpx.Response(200, json=WRONG_REF_SCHEMA)
    )
    mock_router.get("/dataschema/v1/datasetId/901").mock(
        return_value=httpx.Response(200, json=RIGHT_REF_SCHEMA)
    )
    return client.for_dataflow(5).for_provider(17)


# ── 1. No silent degradation ──────────────────────────────────────────────────

def test_get_template_picks_the_reference_dataset_that_actually_matches(mock_router, flow):
    """Regression: get_template() used to blindly take refs[0]. On real dataflows
    the codelists live elsewhere (dataflow 2003 needs refs[3])."""
    pytest.importorskip("polars")
    _mock_reference_export(mock_router, 901, "Categories.csv", b"code\nA\nB\n")

    templates = flow.get_template(dataset_id=100)

    # Enum, not plain string -> the correct reference dataset (901) was used.
    dtype = templates["Table1a"].schema["category"]
    assert "Enum" in str(dtype), f"expected Enum, got {dtype}"
    assert "A" in str(dtype) and "B" in str(dtype)


def test_get_codelists_warns_when_fields_cannot_be_resolved(mock_router, flow):
    pytest.importorskip("polars")
    _mock_reference_export(mock_router, 900, "Units.csv", b"unit\nkg\n")

    with pytest.warns(UserWarning, match="unresolved"):
        values = flow.get_codelists(dataset_id=100, ref_dataset_id=900)

    assert values == {}, "no LINK field is satisfied by this reference dataset"


def test_get_codelists_strict_raises_instead_of_warning(mock_router, flow):
    pytest.importorskip("polars")
    _mock_reference_export(mock_router, 900, "Units.csv", b"unit\nkg\n")

    with pytest.raises(reportnet.CodelistResolutionError) as excinfo:
        flow.get_codelists(dataset_id=100, ref_dataset_id=900, strict=True)

    assert "category" in excinfo.value.unresolved


def test_get_codelists_is_quiet_when_resolution_is_complete(mock_router, flow):
    pytest.importorskip("polars")
    _mock_reference_export(mock_router, 901, "Categories.csv", b"code\nA\nB\n")

    import warnings as _w
    with _w.catch_warnings():
        _w.simplefilter("error")          # any warning fails the test
        values = flow.get_codelists(dataset_id=100, ref_dataset_id=901)

    assert values == {"category": ["A", "B"]}


def test_get_template_warns_when_the_reference_export_fails(mock_router, flow):
    """A 403 on the reference export must not silently yield string columns."""
    pytest.importorskip("polars")
    mock_router.get("/dataset/v4/etlExport/901").mock(return_value=httpx.Response(403))

    with pytest.warns(UserWarning, match="any string"):
        templates = flow.get_template(dataset_id=100)

    assert templates["Table1a"].schema["category"] == __import__("polars").String


def test_get_template_strict_raises_when_the_reference_export_fails(mock_router, flow):
    pytest.importorskip("polars")
    mock_router.get("/dataset/v4/etlExport/901").mock(return_value=httpx.Response(403))

    with pytest.raises(reportnet.CodelistResolutionError):
        flow.get_template(dataset_id=100, strict=True)


# ── 2. Logging ────────────────────────────────────────────────────────────────

def test_requests_are_logged_at_debug(mock_router, flow, caplog):
    with caplog.at_level(logging.DEBUG, logger="reportnet"):
        flow.get_dataflow()
    assert any("/dataflow/v1/5" in r.getMessage() for r in caplog.records)


def test_retries_are_logged_at_warning(mock_router, client, caplog):
    from unittest.mock import patch

    route = mock_router.get("/dataflow/v1/9")
    route.side_effect = [httpx.Response(503), httpx.Response(200, json={"id": 9})]

    with patch("reportnet._http.time.sleep"):
        with caplog.at_level(logging.WARNING, logger="reportnet"):
            client.get_dataflow(dataflow_id=9)

    assert any("retrying" in (r.getMessage()) for r in caplog.records)


def test_reference_dataset_selection_is_logged(mock_router, flow, caplog):
    pytest.importorskip("polars")
    _mock_reference_export(mock_router, 901, "Categories.csv", b"code\nA\n")

    with caplog.at_level(logging.INFO, logger="reportnet"):
        flow.get_template(dataset_id=100)

    messages = [r.getMessage() for r in caplog.records]
    assert any("selected reference dataset 901" in m for m in messages), messages


def test_library_is_silent_without_logging_configuration(mock_router, flow, capsys):
    """A NullHandler must keep the library quiet for apps that don't opt in."""
    flow.get_dataflow()
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


# ── 3. Name-based lookup ──────────────────────────────────────────────────────

def test_dataset_looks_up_by_table_name(flow):
    ds = flow.dataset("Table1a")
    assert ds.id == 100
    assert ds.provider_id == 17


def test_dataset_lookup_is_case_insensitive(flow):
    assert flow.dataset("table1A").id == 100


def test_dataset_lookup_is_scoped_to_this_provider(flow):
    """Italy also has a Table1a (id=102); a scoped client must not return it."""
    assert flow.dataset("Table1a").id == 100


def test_dataset_unknown_name_lists_the_available_ones(flow):
    with pytest.raises(KeyError) as excinfo:
        flow.dataset("Nope")
    assert "Table1a" in str(excinfo.value)
    assert "Table7" in str(excinfo.value)


def test_dataset_requires_a_provider_scope(mock_router, client):
    with pytest.raises(ValueError, match="provider-scoped"):
        client.for_dataflow(5).dataset("Table1a")


def test_datasets_by_table(flow):
    mapping = flow.datasets_by_table()
    assert set(mapping) == {"Table1a", "Table7"}
    assert mapping["Table7"].id == 101


def test_reference_dataset_by_partial_name(flow):
    ref = flow.reference_dataset("codelist")
    assert ref.id == 901


def test_reference_dataset_by_exact_name(flow):
    assert flow.reference_dataset("Reference Dataset - Units").id == 900


def test_reference_dataset_ambiguous_partial_raises(flow):
    with pytest.raises(KeyError, match="matches 2 reference datasets"):
        flow.reference_dataset("Reference Dataset")


def test_reference_dataset_unknown_lists_available(flow):
    with pytest.raises(KeyError) as excinfo:
        flow.reference_dataset("nothing")
    assert "Reference Dataset - Codelist" in str(excinfo.value)
