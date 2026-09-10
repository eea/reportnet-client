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


# ── Dual-role keys: custodian probe, reporter write ───────────────────────────


def test_import_flips_to_dataset_owner_on_unscoped_client(mock_router, client):
    """An account that is *both* custodian and lead reporter passes the
    custodian probe, so providerId is withheld and the write 403s. Verified
    live on dataflow 2003. The flip must recover the provider from the dataset
    itself, because an unscoped client has none stored to flip to."""
    dc = client.for_dataflow(dataflow_id=5)  # no provider_id
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 5,
                "bigData": True,
                "reportingDatasets": [
                    {"id": 10, "dataProviderId": 56, "dataSetName": "France"},
                    {"id": 11, "dataProviderId": 64, "dataSetName": "Italy"},
                ],
            },
        )
    )
    route = mock_router.post("/dataset/v2/importFileData/10").mock(
        side_effect=[
            httpx.Response(403, text="Forbidden"),
            httpx.Response(200, json=JOB_RESPONSE),
        ]
    )
    dc.import_file(dataset_id=10, file=b"data")
    assert len(route.calls) == 2
    assert "providerId" not in str(route.calls[0].request.url)
    assert route.calls[1].request.url.params["providerId"] == "56"


def test_import_flip_picks_the_owning_provider_not_just_any(mock_router, client):
    """The recovered provider must be the one owning *this* dataset — Italy's
    dataset must not be retried as France."""
    dc = client.for_dataflow(dataflow_id=5)
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 5,
                "bigData": True,
                "reportingDatasets": [
                    {"id": 10, "dataProviderId": 56, "dataSetName": "France"},
                    {"id": 11, "dataProviderId": 64, "dataSetName": "Italy"},
                ],
            },
        )
    )
    route = mock_router.post("/dataset/v2/importFileData/11").mock(
        side_effect=[
            httpx.Response(403, text="Forbidden"),
            httpx.Response(200, json=JOB_RESPONSE),
        ]
    )
    dc.import_file(dataset_id=11, file=b"data")
    assert route.calls[1].request.url.params["providerId"] == "64"


def test_import_still_raises_when_owner_is_unknowable(mock_router, client):
    """A reference dataset has no owning provider, so there is nothing to flip
    to and the original 403 must surface rather than being retried blindly."""
    dc = client.for_dataflow(dataflow_id=5)
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True, "reportingDatasets": []})
    )
    route = mock_router.post("/dataset/v2/importFileData/99").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    with pytest.raises(Exception):
        dc.import_file(dataset_id=99, file=b"data")
    assert len(route.calls) == 1, "must not retry when there is no alternative"


# ── Reference datasets must be unlocked to accept an import ───────────────────


def _dataflow_with_locked_reference(updatable=False):
    return {
        "id": 5, "bigData": True,
        "referenceDatasets": [{
            "id": 20, "dataSetName": "Reference Dataset - Descriptive",
            "datasetSchema": "s1", "updatable": updatable,
        }],
    }


def _schema_one_table():
    return {
        "idDataSetSchema": "s1", "nameDatasetSchema": "Ref", "description": "",
        "tableSchemas": [{
            "idTableSchema": "t1", "nameTableSchema": "T",
            "recordSchema": {"fieldSchema": [{"id": "f1", "name": "a", "type": "TEXT"}]},
        }],
    }


def test_import_frames_unlocks_and_relocks_a_reference_dataset(mock_router, client):
    """A locked reference dataset returns HTTP 200 and then CANCELED with
    'Import is not allowed for this dataset.' — verified live on 2003."""
    pl = pytest.importorskip("polars")
    dc = client.for_dataflow(dataflow_id=5)
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json=_dataflow_with_locked_reference())
    )
    mock_router.get("/dataschema/v1/datasetId/20").mock(
        return_value=httpx.Response(200, json=_schema_one_table())
    )
    lock = mock_router.put("/referenceDataset/20").mock(return_value=httpx.Response(200))
    mock_router.post("/dataset/v2/importFileData/20").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    mock_router.get("/orchestrator/jobs/pollForJobStatus/1").mock(
        return_value=httpx.Response(200, json={"status": "FINISHED"})
    )
    dc.import_frames(dataset_id=20, frames={"T": pl.DataFrame({"a": ["x"]})})
    states = [c.request.url.params["updatable"] for c in lock.calls]
    assert states == ["true", "false"], "unlock before import, restore after"


def test_import_frames_relocks_even_when_the_import_fails(mock_router, client):
    """The lock must be restored on failure, or the dataset is left open."""
    pl = pytest.importorskip("polars")
    dc = client.for_dataflow(dataflow_id=5)
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json=_dataflow_with_locked_reference())
    )
    mock_router.get("/dataschema/v1/datasetId/20").mock(
        return_value=httpx.Response(200, json=_schema_one_table())
    )
    lock = mock_router.put("/referenceDataset/20").mock(return_value=httpx.Response(200))
    mock_router.post("/dataset/v2/importFileData/20").mock(
        return_value=httpx.Response(500, text="boom")
    )
    with pytest.raises(Exception):
        dc.import_frames(dataset_id=20, frames={"T": pl.DataFrame({"a": ["x"]})})
    assert [c.request.url.params["updatable"] for c in lock.calls] == ["true", "false"]


def test_import_frames_leaves_an_already_unlocked_reference_dataset_alone(mock_router, client):
    """Never lock something the caller deliberately left open."""
    pl = pytest.importorskip("polars")
    dc = client.for_dataflow(dataflow_id=5)
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json=_dataflow_with_locked_reference(updatable=True))
    )
    mock_router.get("/dataschema/v1/datasetId/20").mock(
        return_value=httpx.Response(200, json=_schema_one_table())
    )
    lock = mock_router.put("/referenceDataset/20").mock(return_value=httpx.Response(200))
    mock_router.post("/dataset/v2/importFileData/20").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    mock_router.get("/orchestrator/jobs/pollForJobStatus/1").mock(
        return_value=httpx.Response(200, json={"status": "FINISHED"})
    )
    dc.import_frames(dataset_id=20, frames={"T": pl.DataFrame({"a": ["x"]})})
    assert not lock.calls, "no lock change when already unlocked"


def test_job_failure_surfaces_reportnet_reason(mock_router, client):
    """The reason is in the poll response's `info`; without it the status alone
    is unactionable. This cost hours of debugging on 2003."""
    from reportnet.exceptions import JobFailedError
    mock_router.post("/dataset/v2/importFileData/10").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    mock_router.get("/orchestrator/jobs/pollForJobStatus/1").mock(
        return_value=httpx.Response(200, json={
            "status": "CANCELED",
            "info": "Import files contain incorrect headers.",
        })
    )
    handle = client.import_file(dataset_id=10, dataflow_id=5, file=b"a\nx")
    with pytest.raises(JobFailedError) as exc:
        handle.wait(poll_interval=0)
    assert exc.value.info == "Import files contain incorrect headers."
    assert "incorrect headers" in str(exc.value)


def test_import_frames_warns_when_a_required_field_is_added_empty(mock_router, client, caplog):
    """Alignment fixes shape, not content. A required field added empty imports
    fine and fails validation later — the warning has to come now. On 2003
    `repCode` is required in all 12 tables and absent from most source extracts."""
    pl = pytest.importorskip("polars")
    import logging
    dc = client.for_dataflow(dataflow_id=5)
    schema = {
        "idDataSetSchema": "s1", "nameDatasetSchema": "D", "description": "",
        "tableSchemas": [{
            "idTableSchema": "t1", "nameTableSchema": "T",
            "recordSchema": {"fieldSchema": [
                {"id": "f1", "name": "repCode", "type": "TEXT", "required": True},
                {"id": "f2", "name": "note", "type": "TEXT", "required": False},
                {"id": "f3", "name": "a", "type": "TEXT", "required": False},
            ]},
        }],
    }
    mock_router.get("/dataflow/v1/5").mock(return_value=httpx.Response(200, json={"id": 5}))
    mock_router.get("/dataschema/v1/datasetId/10").mock(
        return_value=httpx.Response(200, json=schema)
    )
    mock_router.post("/dataset/v2/importFileData/10").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    mock_router.get("/orchestrator/jobs/pollForJobStatus/1").mock(
        return_value=httpx.Response(200, json={"status": "FINISHED"})
    )
    with caplog.at_level(logging.INFO, logger="reportnet.dataflow"):
        dc.import_frames(dataset_id=10, frames={"T": pl.DataFrame({"a": ["x"]})})
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("repCode" in m and "required" in m for m in warnings), warnings
    assert not any("note" in m for m in warnings), "optional fields must not warn"
