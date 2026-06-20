import io

import httpx
import pytest

from reportnet import JobHandle

POLLING_URL = "/orchestrator/jobs/pollForJobStatus/100?datasetId=1&dataflowId=2"
JOB_RESPONSE = {"jobId": 100, "pollingUrl": POLLING_URL}


def test_import_file_bytes(mock_router, client):
    mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    handle = client.import_file(dataset_id=1, dataflow_id=2, file=b"col1,col2\nval1,val2")
    assert isinstance(handle, JobHandle)
    assert handle.job_id == 100
    assert handle.polling_url == POLLING_URL


def test_import_file_io(mock_router, client):
    mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    handle = client.import_file(dataset_id=1, dataflow_id=2, file=io.BytesIO(b"col1\nval1"))
    assert handle.job_id == 100


def test_import_file_polars_dataframe(mock_router, client):
    pl = pytest.importorskip("polars")
    mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    df = pl.DataFrame({"col1": ["val1"], "col2": ["val2"]})
    handle = client.import_file(dataset_id=1, dataflow_id=2, file=df)
    assert handle.job_id == 100


def test_import_file_pandas_dataframe(mock_router, client):
    pytest.importorskip("narwhals")
    pd = pytest.importorskip("pandas")
    mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    df = pd.DataFrame({"col1": ["val1"], "col2": ["val2"]})
    handle = client.import_file(dataset_id=1, dataflow_id=2, file=df)
    assert handle.job_id == 100


def test_import_file_sends_auth_header(mock_router, client):
    route = mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    client.import_file(dataset_id=1, dataflow_id=2, file=b"data")
    assert route.calls[0].request.headers["Authorization"] == "ApiKey test-key"


def test_import_file_replace_param(mock_router, client):
    route = mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    client.import_file(dataset_id=1, dataflow_id=2, file=b"data", replace=True)
    assert "replace=true" in str(route.calls[0].request.url)


def test_etl_import(mock_router, client):
    mock_router.post("/dataset/v1/1/etlImport").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    handle = client.etl_import(
        dataset_id=1,
        dataflow_id=2,
        tables=[{"tableName": "t", "records": []}],
    )
    assert handle.job_id == 100


def test_import_raises_auth_error(mock_router, client):
    from reportnet import AuthError

    mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(401, text="Unauthorized")
    )
    with pytest.raises(AuthError) as exc_info:
        client.import_file(dataset_id=1, dataflow_id=2, file=b"data")
    assert exc_info.value.status_code == 401


def test_import_dataframe_uses_pipe_delimiter_by_default(mock_router, client):
    """DataFrame serialised to CSV must use the same delimiter sent to the API."""
    pl = pytest.importorskip("polars")

    captured: list[bytes] = []

    def _capture(request, route):  # noqa: ARG001
        captured.append(request.content)
        return httpx.Response(200, json=JOB_RESPONSE)

    mock_router.post("/dataset/v2/importFileData/1").mock(side_effect=_capture)
    df = pl.DataFrame({"col1": ["a,b"], "col2": ["c"]})
    client.import_file(dataset_id=1, dataflow_id=2, file=df)

    body = captured[0].decode()
    # The CSV must use | as separator and the query string must say delimiter=%7C (|)
    assert "col1|col2" in body or b"col1|col2".decode() in body
    # The default delimiter param must also be | (url-encoded or literal)
    assert "delimiter=%7C" in str(
        mock_router.calls[0].request.url
    ) or "delimiter=|" in str(mock_router.calls[0].request.url)


def test_import_dataframe_respects_custom_delimiter(mock_router, client):
    pl = pytest.importorskip("polars")

    captured: list[bytes] = []

    def _capture(request, route):  # noqa: ARG001
        captured.append(request.content)
        return httpx.Response(200, json=JOB_RESPONSE)

    mock_router.post("/dataset/v2/importFileData/1").mock(side_effect=_capture)
    df = pl.DataFrame({"col1": ["a"], "col2": ["b"]})
    client.import_file(dataset_id=1, dataflow_id=2, file=df, delimiter=",")

    body = captured[0].decode()
    assert "col1,col2" in body
