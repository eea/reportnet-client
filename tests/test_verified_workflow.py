"""Contract tests: real HTTP shapes with known input, failures and readbacks."""
import csv
import io
import json
import warnings
import zipfile

import httpx
import polars as pl
import pytest

import reportnet
from reportnet.verification import verify_export


def _table(name, fields):
    return {"idTableSchema": name.lower(), "nameTableSchema": name,
            "recordSchema": {"fieldSchema": [
                {"id": f"{name}-{col}", "name": col, "type": kind, "required": required}
                for col, kind, required in fields]}}


SCHEMA = {"idDataSetSchema": "schema", "nameDatasetSchema": "Reporting", "tableSchemas": [
    _table("Items", [("code", "TEXT", True), ("amount", "NUMBER_DECIMAL", False)]),
    _table("Meta", [("note", "TEXT", False)]),
]}
BASE = {"Items": b"record_id,code,amount\n1,old,1\n", "Meta": b"note\nkeep\n"}
AFTER = {"Items": b"record_id,code,amount\n3,new,2\n1,old,1\n2,new,2\n",
         "Meta": b"note\nkeep\n"}


def archive(tables):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in tables.items():
            zf.writestr(name + ".csv", content)
    return buf.getvalue()


def routes(router, *, snapshots=(BASE, AFTER), big=True, reporter=True, validation=None):
    state = {"exports": 0}
    dataflow = {"id": 2, "bigData": big, "reportingDatasets": [
        {"id": 100, "dataProviderId": 64, "dataSetName": "IT",
         "datasetSchema": "schema", "nameDatasetSchema": "Reporting"}]}
    router.get("/dataflow/v1/2").mock(side_effect=lambda request: httpx.Response(
        403 if reporter and "providerId" not in request.url.params else 200, json=dataflow))
    router.get("/dataflow/v1/2/getmetabase").respond(200, json=dataflow)
    router.get("/representative/v1/dataflow/2").respond(200, json=[{"dataProviderId": 64}])
    schema_route = router.get("/dataschema/v1/datasetId/100").respond(200, json=SCHEMA)

    def export(request):
        expected_pid = "64" if reporter or not big else None
        assert request.url.params.get("providerId") == expected_pid
        index = state["exports"]
        state["exports"] += 1
        job_id = 10 + index
        router.get(f"/poll/{job_id}").respond(
            200, json={"status": "FINISHED", "downloadUrl": f"/download/{job_id}"})
        payload = archive(snapshots[index])
        if not big:
            tables = []
            for name, data in snapshots[index].items():
                rows = csv.DictReader(io.StringIO(data.decode()))
                tables.append({"tableName": name, "records": [
                    {"fields": [{"fieldName": k, "value": v} for k, v in row.items()]}
                    for row in rows]})
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("export.json", json.dumps({"tables": tables}))
            payload = buf.getvalue()
        router.get(f"/download/{job_id}").respond(200, content=payload)
        return httpx.Response(200, json={"jobId": job_id, "pollingUrl": f"/poll/{job_id}"})

    export_route = router.get(f"/dataset/v{4 if big else 3}/etlExport/100").mock(side_effect=export)
    imported = router.post("/dataset/v2/importFileData/100").respond(
        200, json={"jobId": 400, "pollingUrl": "/poll/400"})
    router.get("/poll/400").respond(200, json={"status": "FINISHED"})
    validate = router.put("/orchestrator/jobs/addValidationJob/100").respond(200, json=500)
    router.get("/orchestrator/jobs/pollForJobStatus/500").respond(200, json={"status": "FINISHED"})
    suffix = "DL" if big else ""
    router.get(f"/validation/listGroupValidations{suffix}/100").respond(
        200, json=validation if validation is not None else
        {"idDataset": 100, "errors": [], "totalErrors": 0})
    return schema_route, export_route, imported, validate


def inputs():
    return {"Items": pl.DataFrame({"code": ["new", "new"], "amount": [2.0, 2.0]})}


@pytest.mark.parametrize("big", [True, False])
@pytest.mark.parametrize("reporter", [True, False])
def test_complete_reporter_workflow(mock_router, client, big, reporter):
    schema, exported, imported, validated = routes(mock_router, big=big, reporter=reporter)
    me = client.for_dataflow(2).for_provider(64)
    result = me.prepare_submission(dataset_id=100, frames=inputs(), poll_interval=0)
    assert result.ready_for_review
    assert result.import_job_ids == (400,)
    assert result.readback.ok
    assert result.export.verification.row_counts == {"Items": 3, "Meta": 1}
    assert imported.call_count == validated.call_count == 1
    assert exported.call_count == 2
    assert b"code|amount\nnew|2.0\nnew|2.0" in imported.calls[0].request.content
    assert any(e.operation == "submission_readback" and e.workflow_verified is True
               for e in me.permission_evidence())


@pytest.mark.parametrize("after", [
    BASE,  # FINISHED import wrote nothing.
    {"Items": b"code,amount\nold,1\nnew,2\nwrong,2\n", "Meta": BASE["Meta"]},
    {"Items": AFTER["Items"], "Meta": b"note\nchanged concurrently\n"},
])
def test_readback_checks_values_duplicates_and_untouched_tables(mock_router, client, after):
    _, _, imported, validated = routes(mock_router, snapshots=(BASE, after))
    me = client.for_dataflow(2).for_provider(64)
    with pytest.raises(reportnet.ReadbackVerificationError) as error:
        me.prepare_submission(dataset_id=100, frames=inputs(), poll_interval=0)
    assert not error.value.verification.ok
    assert imported.call_count == 1
    assert validated.call_count == 0
    assert "not rolled back" in str(error.value)
    assert me.permission_evidence()[-1].workflow_verified is False


def test_replace_checks_only_replaced_tables_but_preserves_others(mock_router, client):
    after = {"Items": b"code,amount\nnew,2\nnew,2\n", "Meta": BASE["Meta"]}
    _, _, imported, _ = routes(mock_router, snapshots=(BASE, after))
    result = client.for_dataflow(2).for_provider(64).prepare_submission(
        dataset_id=100, frames=inputs(), replace=True, poll_interval=0)
    assert result.ready_for_review
    assert imported.calls[0].request.url.params["replace"] == "true"


@pytest.mark.parametrize("frames", [
    {**inputs(), "Unknown": pl.DataFrame({"x": [1]})},
    {**inputs(), "Meta": pl.DataFrame({"extra": [1]})},
    {"Items": pl.DataFrame({"code": [None], "amount": [2]})},
    {"Items": pl.DataFrame({"code": ["x"], "amount": ["not numeric"]})},
])
def test_all_tables_preflight_before_any_write(mock_router, client, frames):
    _, exported, imported, validated = routes(mock_router)
    with pytest.raises((ValueError, ArithmeticError)):
        client.for_dataflow(2).for_provider(64).prepare_submission(
            dataset_id=100, frames=frames, poll_interval=0)
    assert exported.call_count == imported.call_count == validated.call_count == 0


def test_wrong_provider_dataset_stops_before_writes(mock_router, client):
    _, exported, imported, _ = routes(mock_router)
    with pytest.raises(ValueError, match="not a reporting dataset"):
        client.for_dataflow(2).for_provider(64).prepare_submission(dataset_id=999, frames=inputs())
    assert exported.call_count == imported.call_count == 0


def test_validation_blockers_are_not_ready_for_review(mock_router, client):
    routes(mock_router, validation={"idDataset": 100, "errors": [
        {"levelError": "BLOCKER", "message": "bad data", "numberOfRecords": "1"}]})
    result = client.for_dataflow(2).for_provider(64).prepare_submission(
        dataset_id=100, frames=inputs(), poll_interval=0)
    assert not result.ready_for_review
    assert result.validation.has_blockers


@pytest.mark.parametrize("raw", [{}, {"errors": [], "totalErrors": 2},
                                  {"errors": [], "idDataset": 999}])
def test_unrecognised_validation_response_cannot_pass(mock_router, client, raw):
    routes(mock_router, validation=raw)
    with pytest.raises(reportnet.ReportnetError):
        client.for_dataflow(2).for_provider(64).prepare_submission(
            dataset_id=100, frames=inputs(), poll_interval=0)


CODELIST_SCHEMA = {"idDataSetSchema": "schema", "nameDatasetSchema": "Reporting",
                   "tableSchemas": [
                       _table("Items", [("code", "CODELIST", True),
                                        ("amount", "NUMBER_DECIMAL", False)]),
                       _table("Meta", [("note", "TEXT", False)])]}


def codelist_routes(router):
    """Every real reporting table has LINK/CODELIST fields; the base schema has none."""
    result = routes(router)
    router.get("/dataschema/v1/datasetId/100").respond(200, json=CODELIST_SCHEMA)
    return result


def test_unresolved_codelists_warn_and_log_but_still_submit(mock_router, client, caplog):
    """Default matches get_codelists()/get_template(): degrade loudly, not fatally.

    A reporter on dataflow 2003 resolves 0/10 LINK fields, so raising by default
    would make the primary workflow fail closed on real data.
    """
    _, _, imported, validated = codelist_routes(mock_router)
    with pytest.warns(UserWarning, match="code-list"):
        result = client.for_dataflow(2).for_provider(64).prepare_submission(
            dataset_id=100, frames=inputs(), poll_interval=0)
    assert result.ready_for_review
    assert imported.call_count == validated.call_count == 1
    assert any("code-list" in record.message for record in caplog.records)


def test_strict_codelists_refuses_before_any_write(mock_router, client):
    _, exported, imported, validated = codelist_routes(mock_router)
    with pytest.raises(reportnet.CodelistResolutionError) as error:
        client.for_dataflow(2).for_provider(64).prepare_submission(
            dataset_id=100, frames=inputs(), strict_codelists=True, poll_interval=0)
    assert error.value.unresolved == ["code"]
    assert exported.call_count == imported.call_count == validated.call_count == 0


def test_supplied_codelists_are_checked_and_silence_the_warning(mock_router, client):
    codelist_routes(mock_router)
    me = client.for_dataflow(2).for_provider(64)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert me.prepare_submission(dataset_id=100, frames=inputs(), strict_codelists=True,
                                     codelists={"code": ["new", "old"]},
                                     poll_interval=0).ready_for_review
    # Supplying them also enforces them: an out-of-list value is a preflight failure.
    with pytest.raises(ValueError, match="code"):
        me.prepare_submission(dataset_id=100, codelists={"code": ["old"]},
                              frames={"Items": pl.DataFrame({"code": ["absent"],
                                                             "amount": [2.0]})},
                              poll_interval=0)


def test_checked_export_rejects_unexpected_tables_and_records_evidence(mock_router, client):
    _, exported, _, _ = routes(mock_router, snapshots=({**BASE, "OtherDataset": b"secret\n"},))
    me = client.for_dataflow(2).for_provider(64)
    with pytest.raises(reportnet.ExportVerificationError) as error:
        me.export_frames(dataset_id=100, poll_interval=0)
    assert error.value.verification.unexpected_tables == ("OtherDataset",)
    evidence = [e for e in me.permission_evidence() if e.operation == "etl_export"][0]
    assert evidence.request_accepted is True
    assert evidence.payload_verified is False
    assert evidence.workflow_verified is None
    assert evidence.provider_id == 64 and evidence.version == 4
    assert exported.call_count == 1


def test_non_strict_export_warns_logs_and_keeps_all_frames(mock_router, client, caplog):
    routes(mock_router, snapshots=({**BASE, "Unexpected": b"x\n1\n"},))
    with pytest.warns(UserWarning, match="unexpected tables"):
        result = client.for_dataflow(2).for_provider(64).export_frames(
            dataset_id=100, strict=False, poll_interval=0)
    assert "Unexpected" in result.frames
    assert not result.verification.ok
    assert any("MISMATCH" in record.message for record in caplog.records)


def test_empty_tables_are_explicit_but_structurally_valid():
    schema = reportnet.DatasetSchema.from_dict(SCHEMA)
    frames = {"Items": pl.DataFrame(schema={"code": pl.String, "amount": pl.Float64}),
              "Meta": pl.DataFrame(schema={"note": pl.String})}
    report = verify_export(frames, schema, dataset_id=100)
    assert report.ok and report.empty_tables == ("Items", "Meta")
    frames["Items"] = pl.DataFrame()
    assert verify_export(frames, schema, dataset_id=100).missing_columns == {
        "Items": ("amount", "code")}


def test_single_table_export_checks_only_requested_table(mock_router, client):
    routes(mock_router, snapshots=({"Items": BASE["Items"]},))
    result = client.for_dataflow(2).for_provider(64).export_frames(
        dataset_id=100, table_schema_id="items", poll_interval=0)
    assert result.verification.ok
    assert result.verification.expected_tables == ("Items",)


def test_get_validation_results_reads_without_starting_a_job(mock_router, client):
    """Resubmitting to wait is a 423 and an error banner in the RN3 UI."""
    _, _, _, validate = routes(mock_router, validation={
        "idDataset": 100, "totalErrors": 4, "errors": [
            {"levelError": "ERROR", "message": "Data in the dataset are not coherent",
             "nameTableSchema": "Items", "nameFieldSchema": "code",
             "numberOfRecords": "4", "shortCode": "RelationalTest-12"}]})
    me = client.for_dataflow(2).for_provider(64)

    result = me.get_validation_results(dataset_id=100)
    assert validate.call_count == 0          # no job submitted
    assert [i.level for i in result.issues] == ["ERROR"]
    assert result.issues[0].record_count == 4
    assert result.issues[0].short_code == "RelationalTest-12"
    assert result.has_errors and not result.has_blockers
    assert result.raw["totalErrors"] == 4


def test_get_validation_results_is_empty_while_a_run_is_in_progress(mock_router, client):
    """RN3 clears the listing mid-run: empty is not the same as clean."""
    routes(mock_router, validation={"idDataset": 100, "errors": []})
    result = client.for_dataflow(2).for_provider(64).get_validation_results(dataset_id=100)
    assert result.ok and not result.issues
    # totalErrors absent is how the caller tells "not finished" from "nothing wrong".
    assert result.raw.get("totalErrors") is None


def test_permission_evidence_does_not_probe_or_invent_permissions(mock_router, client):
    assert client.for_dataflow(2).permission_evidence() == ()
    assert len(mock_router.calls) == 0


def test_raw_export_acceptance_is_not_payload_verification(mock_router, client):
    routes(mock_router, snapshots=(BASE,))
    client.for_dataflow(2).for_provider(64).etl_export(dataset_id=100)
    evidence = [e for e in client.permission_evidence(dataflow_id=2) if e.operation == "etl_export"]
    assert evidence[0].request_accepted is True
    assert evidence[0].payload_verified is evidence[0].workflow_verified is None


def test_download_auth_failure_does_not_start_another_export(mock_router, client):
    _, exported, _, _ = routes(mock_router)
    # Override the dynamically installed download route after export submission.
    original = client.etl_export

    def start(**kwargs):
        handle = original(**kwargs)
        mock_router.get("/download/10").respond(403)
        return handle

    from unittest.mock import patch
    with patch.object(client, "etl_export", side_effect=start):
        with pytest.raises(reportnet.AuthError):
            client.for_dataflow(2).for_provider(64).export_frames(dataset_id=100, poll_interval=0)
    assert exported.call_count == 1


# ── Stale validation results announce themselves ──────────────────────────────

VALIDATION_LISTING = {
    "idDataset": 10, "errors": [], "totalRecords": 69, "totalErrors": 50,
}


def _jobs(*rows):
    return {"jobsList": [
        {"id": i, "jobType": "VALIDATION", "jobStatus": st, "datasetId": 10,
         "dateAdded": 1789000000000, "dateStatusChanged": 1789000001000, "jobInfo": None}
        for i, st in rows
    ]}


def test_results_are_flagged_stale_while_a_newer_validation_runs(mock_router, client, caplog):
    """Reportnet keeps serving the PREVIOUS run's results while a new validation
    is in flight — no timestamp, no run id, identical numbers. Verified on 2003:
    a run against changed data reported the earlier totals for over an hour."""
    import logging
    dc = client.for_dataflow(dataflow_id=5)
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    mock_router.get("/validation/listGroupValidationsDL/10").mock(
        return_value=httpx.Response(200, json=VALIDATION_LISTING)
    )
    mock_router.get("/orchestrator/jobs").mock(
        return_value=httpx.Response(200, json=_jobs((250046, "IN_PROGRESS"), (249703, "FINISHED")))
    )
    with caplog.at_level(logging.WARNING, logger="reportnet.dataflow"):
        result = dc.get_validation_results(dataset_id=10)
    assert result.is_stale, "a running validation must mark the listing stale"
    assert result.superseded_by.id == 250046
    assert result.job.id == 249703, "results belong to the last FINISHED run"
    assert any("PREVIOUS run" in r.getMessage() for r in caplog.records)


def test_results_are_not_stale_when_no_validation_is_running(mock_router, client):
    dc = client.for_dataflow(dataflow_id=5)
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    mock_router.get("/validation/listGroupValidationsDL/10").mock(
        return_value=httpx.Response(200, json=VALIDATION_LISTING)
    )
    mock_router.get("/orchestrator/jobs").mock(
        return_value=httpx.Response(200, json=_jobs((249703, "FINISHED")))
    )
    result = dc.get_validation_results(dataset_id=10)
    assert not result.is_stale and result.superseded_by is None
    assert result.job.id == 249703


def test_provenance_is_optional_when_job_history_is_unreadable(mock_router, client):
    """A key that cannot read job history still gets its results, just without
    provenance — never a hard failure on a read-only call."""
    dc = client.for_dataflow(dataflow_id=5)
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    mock_router.get("/validation/listGroupValidationsDL/10").mock(
        return_value=httpx.Response(200, json=VALIDATION_LISTING)
    )
    mock_router.get("/orchestrator/jobs").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    result = dc.get_validation_results(dataset_id=10)
    assert result.job is None and not result.is_stale
    assert result.raw["totalErrors"] == 50


def test_results_are_stale_when_data_was_imported_after_the_last_validation(
    mock_router, client, caplog
):
    """The second staleness mode, and the one that bit on 2003: no validation is
    running, but the data was re-uploaded after the last run finished — so the
    published results describe data that is no longer in the dataset."""
    import logging
    dc = client.for_dataflow(dataflow_id=5)
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    mock_router.get("/validation/listGroupValidationsDL/10").mock(
        return_value=httpx.Response(200, json=VALIDATION_LISTING)
    )
    mock_router.get("/orchestrator/jobs").mock(return_value=httpx.Response(200, json={"jobsList": [
        {"id": 300, "jobType": "IMPORT", "jobStatus": "FINISHED", "datasetId": 10,
         "dateAdded": 1789000000000, "dateStatusChanged": 1789009000000, "jobInfo": None},
        {"id": 249703, "jobType": "VALIDATION", "jobStatus": "FINISHED", "datasetId": 10,
         "dateAdded": 1789000000000, "dateStatusChanged": 1789001000000, "jobInfo": None},
    ]}))
    with caplog.at_level(logging.WARNING, logger="reportnet.dataflow"):
        result = dc.get_validation_results(dataset_id=10)
    assert result.is_stale, "import finished after the validation → results describe old data"
    assert result.superseded_by is None, "nothing is running; staleness is from the import"
    assert any("no longer there" in r.getMessage() for r in caplog.records)


def test_results_are_fresh_when_validation_followed_the_last_import(mock_router, client):
    dc = client.for_dataflow(dataflow_id=5)
    mock_router.get("/dataflow/v1/5").mock(
        return_value=httpx.Response(200, json={"id": 5, "bigData": True})
    )
    mock_router.get("/validation/listGroupValidationsDL/10").mock(
        return_value=httpx.Response(200, json=VALIDATION_LISTING)
    )
    mock_router.get("/orchestrator/jobs").mock(return_value=httpx.Response(200, json={"jobsList": [
        {"id": 249703, "jobType": "VALIDATION", "jobStatus": "FINISHED", "datasetId": 10,
         "dateAdded": 1789000000000, "dateStatusChanged": 1789009000000, "jobInfo": None},
        {"id": 300, "jobType": "IMPORT", "jobStatus": "FINISHED", "datasetId": 10,
         "dateAdded": 1789000000000, "dateStatusChanged": 1789001000000, "jobInfo": None},
    ]}))
    assert not dc.get_validation_results(dataset_id=10).is_stale
