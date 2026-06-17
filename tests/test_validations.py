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
