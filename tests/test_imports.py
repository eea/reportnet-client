import io
import warnings

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


# ── Spatial (geopandas) ────────────────────────────────────────────────────────

def test_to_geodataframe_from_polars():
    """to_geodataframe() converts a polars frame with WKT column to GeoDataFrame."""
    gpd = pytest.importorskip("geopandas")
    pl  = pytest.importorskip("polars")
    import reportnet

    df = pl.DataFrame({
        "id":       ["PA1", "PA2"],
        "geometry_polygon": [
            "MULTIPOLYGON (((0 0, 1 0, 1 1, 0 1, 0 0)))",
            "MULTIPOLYGON (((2 2, 3 2, 3 3, 2 3, 2 2)))",
        ],
        "name": ["Area A", "Area B"],
    })
    gdf = reportnet.to_geodataframe(df, "geometry_polygon")
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 2
    assert gdf.crs.to_epsg() == 4326
    assert gdf.geometry.geom_type.tolist() == ["MultiPolygon", "MultiPolygon"]


@pytest.mark.parametrize("empty_only", [False, True])
def test_to_geodataframe_from_parquet_wkb(empty_only):
    """RN3 v5 geometry is EWKB, with empty bytes for missing values."""
    pytest.importorskip("geopandas")
    pl = pytest.importorskip("polars")
    shapely = pytest.importorskip("shapely")
    import reportnet

    point = shapely.set_srid(shapely.Point(12, 55), 4258)
    encoded = shapely.to_wkb(point, include_srid=True)
    df = pl.DataFrame({"geometry": [b"", None, b"" if empty_only else encoded]})
    gdf = reportnet.to_geodataframe(df, "geometry", crs="EPSG:4258")
    assert gdf.crs.to_epsg() == 4258
    assert gdf.geometry.isna().tolist() == [True, True, empty_only]
    if not empty_only:
        assert gdf.geometry.iloc[2].equals(point)


def test_to_geodataframe_warns_when_ewkb_srid_contradicts_crs(caplog):
    """The default 4326 would silently mislabel dataflow 2003's 4258 geometry."""
    pytest.importorskip("geopandas")
    pl = pytest.importorskip("polars")
    shapely = pytest.importorskip("shapely")
    import reportnet

    point = shapely.set_srid(shapely.Point(12, 55), 4258)
    df = pl.DataFrame({"geometry": [shapely.to_wkb(point, include_srid=True)]})

    with pytest.warns(UserWarning, match="EPSG:4258"):
        gdf = reportnet.to_geodataframe(df, "geometry")
    assert any("EPSG:4258" in record.message for record in caplog.records)
    # The requested CRS is still honoured — the caller is told, not overruled.
    assert gdf.crs.to_epsg() == 4326

    # Naming the real CRS, or shipping WKB without an SRID, is silent.
    caplog.clear()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert reportnet.to_geodataframe(df, "geometry", crs="EPSG:4258").crs.to_epsg() == 4258
        plain = pl.DataFrame({"geometry": [shapely.to_wkb(shapely.Point(12, 55))]})
        assert reportnet.to_geodataframe(plain, "geometry").crs.to_epsg() == 4326
    assert not caplog.records


def test_to_file_tuple_from_geodataframe():
    """import_file() accepts a GeoDataFrame — geometry serialised as WKT."""
    gpd    = pytest.importorskip("geopandas")
    pytest.importorskip("shapely")
    from shapely.geometry import MultiPolygon, Polygon

    from reportnet._util import to_file_tuple

    gdf = gpd.GeoDataFrame(
        {"id": ["PA1"], "name": ["Area A"]},
        geometry=[MultiPolygon([Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])])],
        crs="EPSG:4326",
    )
    fname, data = to_file_tuple(gdf, None)
    text = data.decode()
    assert "geometry" in text
    assert "MULTIPOLYGON" in text.upper()
    assert "PA1" in text


def test_field_type_multipolygon():
    """MULTIPOLYGON and MULTILINESTRING are recognised FieldType values."""
    from reportnet import FieldType
    assert FieldType("MULTIPOLYGON") == FieldType.MULTIPOLYGON
    assert FieldType("MULTILINESTRING") == FieldType.MULTILINESTRING
    assert FieldType("MULTIPOINT") == FieldType.MULTIPOINT


# ── reporter-scoped keys and the BigData preflight ────────────────────────────
# import_file consults is_big_dataflow() to decide whether to send providerId.
# That reads GET /dataflow/v1/{id}, which a reporter-scoped key may not be
# allowed to read — in which case the import used to fail at preflight with a
# 403 naming /dataflow/v1/{id} rather than the endpoint actually being called.

DATAFLOW_BIGDATA = {"id": 2, "name": "df", "bigData": True}
DATAFLOW_CITUS = {"id": 2, "name": "df", "bigData": False}


def test_import_file_omits_provider_id_on_bigdata(mock_router, client):
    mock_router.get("/dataflow/v1/2").mock(
        return_value=httpx.Response(200, json=DATAFLOW_BIGDATA)
    )
    route = mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    scoped = client.for_dataflow(2, provider_id=64)
    scoped.import_file(dataset_id=1, file=b"a|b\n1|2\n")

    assert "providerId" not in route.calls[0].request.url.params


def test_import_file_sends_provider_id_on_citus(mock_router, client):
    mock_router.get("/dataflow/v1/2").mock(
        return_value=httpx.Response(200, json=DATAFLOW_CITUS)
    )
    route = mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    scoped = client.for_dataflow(2, provider_id=64)
    scoped.import_file(dataset_id=1, file=b"a|b\n1|2\n")

    assert route.calls[0].request.url.params["providerId"] == "64"


def test_import_file_works_when_the_dataflow_read_is_forbidden(mock_router, client):
    """A forbidden preflight means a reporter-scoped key, which NEEDS providerId.

    Verified live on dataflow 2003: a Reporter key is 403'd on
    /dataflow/v1/{id}, and its import is 403'd unless providerId is sent
    (job 248505 succeeded once it was).
    """
    mock_router.get("/dataflow/v1/2").mock(return_value=httpx.Response(403, text="Forbidden"))
    # capabilities() falls back to this probe to tell "reporter key" from "bad key"
    mock_router.get("/representative/v1/dataflow/2").mock(
        return_value=httpx.Response(200, json=[])
    )
    route = mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    scoped = client.for_dataflow(2, provider_id=64)
    handle = scoped.import_file(dataset_id=1, file=b"a|b\n1|2\n")

    assert route.call_count == 1, "import must reach the import endpoint, not die at preflight"
    assert route.calls[0].request.url.params["providerId"] == "64"
    assert handle.job_id == 100


def test_import_file_retries_with_the_opposite_provider_id_on_403(mock_router, client):
    """Whether BigData wants providerId depends on the key's role, which cannot
    be queried. A wrong guess must self-correct rather than fail."""
    mock_router.get("/dataflow/v1/2").mock(return_value=httpx.Response(403, text="Forbidden"))
    # capabilities() falls back to this probe to tell "reporter key" from "bad key"
    mock_router.get("/representative/v1/dataflow/2").mock(
        return_value=httpx.Response(200, json=[])
    )
    route = mock_router.post("/dataset/v2/importFileData/1")
    route.side_effect = [
        httpx.Response(403, text="Forbidden"),          # with providerId
        httpx.Response(200, json=JOB_RESPONSE),         # without
    ]
    scoped = client.for_dataflow(2, provider_id=64)
    handle = scoped.import_file(dataset_id=1, file=b"a|b\n1|2\n")

    assert route.call_count == 2
    assert route.calls[0].request.url.params["providerId"] == "64"
    assert "providerId" not in route.calls[1].request.url.params
    assert handle.job_id == 100


def test_import_file_retry_runs_in_the_other_direction_too(mock_router, client):
    """Custodian case: providerId omitted first, then sent on a 403."""
    mock_router.get("/dataflow/v1/2").mock(
        return_value=httpx.Response(200, json={"id": 2, "bigData": True})
    )
    route = mock_router.post("/dataset/v2/importFileData/1")
    route.side_effect = [
        httpx.Response(403, text="Forbidden"),          # without providerId
        httpx.Response(200, json=JOB_RESPONSE),         # with
    ]
    scoped = client.for_dataflow(2, provider_id=64)
    handle = scoped.import_file(dataset_id=1, file=b"a|b\n1|2\n")

    assert route.call_count == 2
    assert "providerId" not in route.calls[0].request.url.params
    assert route.calls[1].request.url.params["providerId"] == "64"
    assert handle.job_id == 100


def test_import_file_explicit_provider_id_is_never_second_guessed(mock_router, client):
    """An explicit choice is honoured — no retry, no flip."""
    from reportnet import AuthError

    route = mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    scoped = client.for_dataflow(2, provider_id=64)

    with pytest.raises(AuthError):
        scoped.import_file(dataset_id=1, file=b"a|b\n1|2\n", provider_id=99)
    assert route.call_count == 1
    assert route.calls[0].request.url.params["providerId"] == "99"


def test_import_file_forbidden_preflight_still_surfaces_a_real_import_403(
    mock_router, client
):
    """Degrading on the preflight must not swallow a genuine 403 from the import.

    Both providerId choices are tried, and when both are refused the error
    still surfaces rather than being masked.
    """
    from reportnet import AuthError

    mock_router.get("/dataflow/v1/2").mock(return_value=httpx.Response(403, text="Forbidden"))
    # capabilities() falls back to this probe to tell "reporter key" from "bad key"
    mock_router.get("/representative/v1/dataflow/2").mock(
        return_value=httpx.Response(200, json=[])
    )
    route = mock_router.post("/dataset/v2/importFileData/1").mock(
        return_value=httpx.Response(403, text="Forbidden")
    )
    scoped = client.for_dataflow(2, provider_id=64)

    with pytest.raises(AuthError):
        scoped.import_file(dataset_id=1, file=b"a|b\n1|2\n")
    assert route.call_count == 2, "both providerId choices tried before giving up"


# ── etlImport countryCode ─────────────────────────────────────────────────────
# Records without countryCode are silently discarded by the API while the job
# still reports FINISHED, so the client warns rather than letting that pass.

def _etl_body(records):
    return [{"tableName": "T", "records": records}]


def test_etl_import_warns_when_records_lack_country_code(mock_router, client):
    mock_router.post("/dataset/v1/1/etlImport").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    records = [{"fields": [{"fieldName": "a", "value": "1"}]}]

    with pytest.warns(UserWarning, match="countryCode"):
        client.etl_import(dataset_id=1, dataflow_id=2, tables=_etl_body(records))


def test_etl_import_does_not_warn_when_country_code_is_present(mock_router, client):
    import warnings

    mock_router.post("/dataset/v1/1/etlImport").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    records = [{"countryCode": "IT", "fields": [{"fieldName": "a", "value": "1"}]}]

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        client.etl_import(dataset_id=1, dataflow_id=2, tables=_etl_body(records))


def test_etl_import_warning_names_the_table_and_counts(mock_router, client):
    mock_router.post("/dataset/v1/1/etlImport").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    records = [
        {"countryCode": "IT", "fields": []},
        {"fields": []},
        {"countryCode": "", "fields": []},
    ]

    with pytest.warns(UserWarning) as caught:
        client.etl_import(dataset_id=1, dataflow_id=2, tables=_etl_body(records))

    message = str(caught[0].message)
    assert "T" in message and "2/3" in message


def test_etl_import_with_no_records_does_not_warn(mock_router, client):
    import warnings

    mock_router.post("/dataset/v1/1/etlImport").mock(
        return_value=httpx.Response(200, json=JOB_RESPONSE)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        client.etl_import(dataset_id=1, dataflow_id=2, tables=_etl_body([]))
