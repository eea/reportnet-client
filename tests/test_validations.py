import httpx

from reportnet import JobHandle

POLLING_URL = "/orchestrator/jobs/pollForJobStatus/300?datasetId=1&dataflowId=2"
JOB_RESPONSE = {"jobId": 300, "pollingUrl": POLLING_URL}
VALIDATION_RESULTS = {"validations": [{"rule": "MANDATORY_FIELD", "count": 3}]}


def test_add_validation_job(mock_router, client):
    mock_router.put("/orchestrator/jobs/addValidationJob/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    handle = client.add_validation_job(dataset_id=1, dataflow_id=2)
    assert isinstance(handle, JobHandle)
    assert handle.job_id == 300


def test_add_validation_job_bare_int_response(mock_router, client):
    # Live API returns a bare integer job ID, not a dict with pollingUrl.
    mock_router.put("/orchestrator/jobs/addValidationJob/1").mock(
        return_value=httpx.Response(200, json=300)
    )
    handle = client.add_validation_job(dataset_id=1, dataflow_id=2)
    assert handle.job_id == 300
    assert "pollForJobStatus/300" in handle.polling_url
    assert "datasetId=1" in handle.polling_url
    assert "dataflowId=2" in handle.polling_url


def test_add_validation_job_with_provider(mock_router, client):
    route = mock_router.put("/orchestrator/jobs/addValidationJob/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    client.add_validation_job(dataset_id=1, dataflow_id=2, provider_id=42)
    assert "providerId=42" in str(route.calls[0].request.url)


def test_list_group_validations(mock_router, client):
    mock_router.get("/validation/listGroupValidations/1").mock(
        return_value=httpx.Response(200, json=VALIDATION_RESULTS)
    )
    result = client.list_group_validations(dataset_id=1, dataflow_id=2)
    assert result == VALIDATION_RESULTS


def test_list_group_validations_dl(mock_router, client):
    mock_router.get("/validation/listGroupValidationsDL/1").mock(
        return_value=httpx.Response(200, json=VALIDATION_RESULTS)
    )
    result = client.list_group_validations_dl(dataset_id=1, dataflow_id=2)
    assert result == VALIDATION_RESULTS


# ── validate() picks the listing endpoint by backend ──────────────────────────
# listGroupValidationsDL is the BigData variant, listGroupValidations the Citus
# one; they are not interchangeable. validate() used to call DL unconditionally,
# which is wrong for every Citus dataflow.

import pytest  # noqa: E402

from reportnet.exceptions import AuthError  # noqa: E402

DATAFLOW_PAYLOAD_CITUS = {"id": 2, "name": "df", "bigData": False}
DATAFLOW_PAYLOAD_BIGDATA = {"id": 2, "name": "df", "bigData": True}
FINISHED = {"status": "FINISHED"}


def _mock_validation_job(mock_router):
    mock_router.put("/orchestrator/jobs/addValidationJob/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    mock_router.get("/orchestrator/jobs/pollForJobStatus/300").mock(
        return_value=httpx.Response(200, json=FINISHED)
    )


def test_validate_uses_citus_endpoint_on_citus_dataflow(mock_router, client):
    _mock_validation_job(mock_router)
    mock_router.get("/dataflow/v1/2").mock(
        return_value=httpx.Response(200, json=DATAFLOW_PAYLOAD_CITUS)
    )
    citus = mock_router.get("/validation/listGroupValidations/1").mock(
        return_value=httpx.Response(200, json=VALIDATION_RESULTS)
    )
    dl = mock_router.get("/validation/listGroupValidationsDL/1").mock(
        return_value=httpx.Response(200, json=VALIDATION_RESULTS)
    )

    result = client.for_dataflow(2).validate(dataset_id=1, poll_interval=0)

    assert citus.call_count == 1
    assert dl.call_count == 0, "Citus dataflow must not use the DL endpoint"
    assert result.dataset_id == 1


def test_validate_uses_dl_endpoint_on_bigdata_dataflow(mock_router, client):
    _mock_validation_job(mock_router)
    mock_router.get("/dataflow/v1/2").mock(
        return_value=httpx.Response(200, json=DATAFLOW_PAYLOAD_BIGDATA)
    )
    citus = mock_router.get("/validation/listGroupValidations/1").mock(
        return_value=httpx.Response(200, json=VALIDATION_RESULTS)
    )
    dl = mock_router.get("/validation/listGroupValidationsDL/1").mock(
        return_value=httpx.Response(200, json=VALIDATION_RESULTS)
    )

    client.for_dataflow(2).validate(dataset_id=1, poll_interval=0)

    assert dl.call_count == 1
    assert citus.call_count == 0


def test_validate_falls_back_when_backend_is_unreadable(mock_router, client):
    """A reporter-scoped key may be 403 on /dataflow/v1/{id}; validation must
    still work rather than failing on the backend lookup."""
    _mock_validation_job(mock_router)
    mock_router.get("/dataflow/v1/2").mock(return_value=httpx.Response(403, text="Forbidden"))
    # is_big_dataflow() falls back to getmetabase, which reporter keys can read;
    # 403 it too so the backend really is undeterminable and the fallback runs.
    mock_router.get("/dataflow/v1/2/getmetabase").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    dl = mock_router.get("/validation/listGroupValidationsDL/1").mock(
        return_value=httpx.Response(404, text="not this backend")
    )
    citus = mock_router.get("/validation/listGroupValidations/1").mock(
        return_value=httpx.Response(200, json=VALIDATION_RESULTS)
    )

    result = client.for_dataflow(2).validate(dataset_id=1, poll_interval=0)

    assert dl.call_count == 1, "DL is tried first"
    assert citus.call_count == 1, "then the Citus endpoint as fallback"
    assert result.raw == VALIDATION_RESULTS


def test_validate_propagates_auth_error_from_the_listing_call(mock_router, client):
    """A 403 on the dataflow read must not mask a genuine 403 on validation."""
    _mock_validation_job(mock_router)
    mock_router.get("/dataflow/v1/2").mock(return_value=httpx.Response(403, text="Forbidden"))
    # is_big_dataflow() falls back to getmetabase, which reporter keys can read;
    # 403 it too so the backend really is undeterminable and the fallback runs.
    mock_router.get("/dataflow/v1/2/getmetabase").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    mock_router.get("/validation/listGroupValidationsDL/1").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    mock_router.get("/validation/listGroupValidations/1").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )

    with pytest.raises(AuthError):
        client.for_dataflow(2).validate(dataset_id=1, poll_interval=0)
