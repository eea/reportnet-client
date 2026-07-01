"""Live integration tests against the real Reportnet API.

Run with:
    uv run pytest -m integration -v

Skipped automatically if the keyring credential for the dataflow is missing.
These tests make real HTTP calls and may take several minutes for BigData jobs.
"""
import io
import zipfile

import pytest

import reportnet

# ── Fixtures ───────────────────────────────────────────────────────────────────
DATAFLOW_ID = 1619
DATASET_ID = 93953       # Table1a dataset (BigData / custodian access)
TABLE_SCHEMA_ID = "68dd41f045f9450001260da7"   # Table1a schema ID from URL tab
COUNTRY_CODE = "AT"      # A reporter present in this dataflow


@pytest.fixture(scope="module")
def client_1619():
    try:
        key = reportnet.get_key(DATAFLOW_ID)
    except KeyError:
        pytest.skip(f"No API key in keyring for dataflow {DATAFLOW_ID}")
    return reportnet.ReportnetClient(api_key=key)


@pytest.fixture(scope="module")
def df_1619(client_1619):
    return client_1619.for_dataflow(DATAFLOW_ID)


# ── Dataflow metadata ──────────────────────────────────────────────────────────

@pytest.mark.integration
def test_get_dataflow_info(df_1619):
    info = df_1619.get_dataflow()
    assert info.id == DATAFLOW_ID
    assert info.name
    assert info.type in ("REPORTING", "BUSINESS", "CITIZEN_SCIENCE", "REFERENCE")
    assert info.status
    print(f"\n  {info.name} ({info.type}, {info.status})")


@pytest.mark.integration
@pytest.mark.xfail(
    reason="/dataflow/private/v1/*/isBigDataflow returned 404 — endpoint not available for this key"
)
def test_is_big_dataflow(df_1619):
    is_big = df_1619.is_big_dataflow()
    print(f"\n  BigData: {is_big}")
    assert isinstance(is_big, bool)


@pytest.mark.integration
def test_get_reporters(df_1619):
    reporters = df_1619.get_reporters()
    assert len(reporters) > 0
    assert all(r.provider_id > 0 for r in reporters)
    print(f"\n  {len(reporters)} reporters")
    for r in reporters[:5]:
        print(f"    provider_id={r.provider_id}  code={r.country_code}  name={r.country_name}")


@pytest.mark.integration
def test_get_reporting_datasets_all(df_1619):
    all_ds = df_1619.get_reporting_datasets()
    assert len(all_ds) > 0
    assert all(isinstance(ds, reportnet.ReportingDataset) for ds in all_ds)
    print(f"\n  {len(all_ds)} reporting datasets total")


@pytest.mark.integration
def test_get_reporting_datasets_scoped(df_1619):
    """Scoped client should return only this provider's datasets."""
    # Find the first reporter present in this dataflow
    reporters = df_1619.get_reporters()
    assert reporters, "no reporters in dataflow"
    pid = reporters[0].provider_id
    scoped = df_1619.for_provider(pid)
    scoped_ds = scoped.get_reporting_datasets()
    assert len(scoped_ds) > 0
    assert all(ds.provider_id == pid for ds in scoped_ds)
    print(f"\n  provider_id={pid}: {len(scoped_ds)} dataset(s)")


@pytest.mark.integration
def test_find_reporter(df_1619):
    """find_reporter() should resolve a country code to a scoped DataflowClient."""
    reporters = df_1619.get_reporters()
    # Find a country code that is in this dataflow
    codes = [r.country_code for r in reporters if r.country_code]
    if not codes:
        pytest.skip("No reporters with known country codes in this dataflow")
    code = codes[0]
    scoped = df_1619.find_reporter(code)
    from reportnet.dataflow import DataflowClient
    assert isinstance(scoped, DataflowClient)
    assert scoped._provider_id is not None
    datasets = scoped.get_reporting_datasets()
    assert len(datasets) > 0
    print(f"\n  find_reporter({code!r}) → provider_id={scoped._provider_id}, "
          f"{len(datasets)} dataset(s)")


@pytest.mark.integration
def test_get_reference_datasets(df_1619):
    refs = df_1619.get_reference_datasets()
    print(f"\n  {len(refs)} reference dataset(s)")
    for r in refs:
        print(f"    id={r.id}  name={r.name}  updatable={r.updatable}")
    assert all(isinstance(r, reportnet.ReferenceDataset) for r in refs)


@pytest.mark.integration
def test_get_test_datasets(df_1619):
    tests = df_1619.get_test_datasets()
    print(f"\n  {len(tests)} test dataset(s)")
    for t in tests:
        print(f"    id={t.id}  name={t.name}")
    assert all(isinstance(t, reportnet.TestDataset) for t in tests)


@pytest.mark.integration
def test_ping(df_1619):
    assert df_1619.ping() is True


# ── Schema and codelists ───────────────────────────────────────────────────────

@pytest.mark.integration
def test_get_schema(df_1619):
    schema = df_1619.get_schema(dataset_id=DATASET_ID)
    assert isinstance(schema, reportnet.DatasetSchema)
    assert schema.name
    assert len(schema.tables) > 0
    for table in schema.tables:
        print(f"\n  table={table.name}  fields={table.column_names()}")
        print(f"    required={table.required_columns()}")


@pytest.mark.integration
def test_to_frame_from_schema(df_1619):
    pytest.importorskip("polars")
    import polars as pl

    schema = df_1619.get_schema(dataset_id=DATASET_ID)
    for table in schema.tables:
        frame = table.to_frame()
        assert isinstance(frame, pl.DataFrame)
        assert frame.shape[0] == 0
        assert set(frame.columns) == set(table.column_names())
        print(f"\n  {table.name}: {frame.schema}")


@pytest.mark.integration
def test_get_codelists(df_1619):
    refs = df_1619.get_reference_datasets()
    if not refs:
        pytest.skip("No reference datasets in this dataflow")
    codelists = df_1619.get_codelists(
        dataset_id=DATASET_ID,
        ref_dataset_id=refs[0].id,
        poll_interval=10.0,
        timeout=300.0,
    )
    assert isinstance(codelists, dict)
    for field_name, values in codelists.items():
        print(f"\n  {field_name}: {len(values)} values  eg. {values[:3]}")
        assert all(isinstance(v, str) for v in values)


@pytest.mark.integration
def test_to_frame_with_codelists(df_1619):
    pytest.importorskip("polars")
    import polars as pl

    refs = df_1619.get_reference_datasets()
    if not refs:
        pytest.skip("No reference datasets in this dataflow")

    schema = df_1619.get_schema(dataset_id=DATASET_ID)
    codelists = df_1619.get_codelists(
        dataset_id=DATASET_ID,
        ref_dataset_id=refs[0].id,
        poll_interval=10.0,
        timeout=300.0,
    )
    for table in schema.tables:
        frame = table.to_frame(codelists=codelists)
        link_cols = [f.name for f in table.fields if f.name in codelists]
        for col in link_cols:
            assert isinstance(frame[col].dtype, pl.Enum), f"{col} should be Enum"
        print(f"\n  {table.name}: Enum cols={link_cols}")


@pytest.mark.integration
def test_validate_frame_with_real_schema(df_1619):
    pytest.importorskip("polars")

    refs = df_1619.get_reference_datasets()
    if not refs:
        pytest.skip("No reference datasets in this dataflow")

    schema = df_1619.get_schema(dataset_id=DATASET_ID)
    codelists = df_1619.get_codelists(
        dataset_id=DATASET_ID,
        ref_dataset_id=refs[0].id,
        poll_interval=10.0,
        timeout=300.0,
    )
    table = schema.tables[0]
    template = table.to_frame(codelists=codelists)
    errors = table.validate_frame(template, codelists=codelists)
    assert errors == [], f"Empty template should have no errors: {errors}"


# ── get_template ──────────────────────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.parametrize("dataset_id,label", [
    (DATASET_ID, "reporting (93953)"),
    (93652,      "data collection (93652)"),
    (93951,      "data schema (93951)"),
])
def test_get_template(df_1619, dataset_id, label):
    """get_template() should return a dict of empty typed DataFrames."""
    pytest.importorskip("polars")
    import polars as pl

    templates = df_1619.get_template(dataset_id=dataset_id, poll_interval=10.0, timeout=300.0)
    assert isinstance(templates, dict), f"Expected dict, got {type(templates)}"
    assert len(templates) > 0, "Expected at least one table"
    for table_name, frame in templates.items():
        assert isinstance(frame, pl.DataFrame), f"{table_name}: expected pl.DataFrame"
        assert frame.shape[0] == 0, f"{table_name}: expected empty frame"
        print(f"\n  [{label}] {table_name}: {frame.schema}")


# ── Export ────────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_etl_export_returns_zip(df_1619):
    handle = df_1619.etl_export(dataset_id=DATASET_ID)
    zip_bytes = handle.result(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  etl_export status: {s}"),
    )
    assert len(zip_bytes) > 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_files = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    assert csv_files, f"ZIP contained no CSVs; files: {zf.namelist()}"
    print(f"  tables: {csv_files}")


@pytest.mark.integration
def test_etl_export_to_frames(df_1619):
    handle = df_1619.etl_export(dataset_id=DATASET_ID)
    frames = handle.to_frames(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  to_frames status: {s}"),
    )
    assert frames, "to_frames() returned empty dict"
    for name, df in frames.items():
        print(f"  {name}: {df.shape[0]} rows × {df.shape[1]} cols")


@pytest.mark.integration
def test_cast_frame_with_real_export(df_1619):
    """Export data then cast numeric/date columns to schema types.

    We do NOT pass codelists here: exported data may contain values that no
    longer match the current codelist (e.g. if the codelist was updated after
    the data was submitted).  cast_frame without codelists only coerces numeric
    and date types — it does not enforce Enum membership.
    """
    pytest.importorskip("polars")

    schema = df_1619.get_schema(dataset_id=DATASET_ID)
    frames = df_1619.etl_export(dataset_id=DATASET_ID).to_frames(
        poll_interval=10.0, timeout=600.0
    )

    for table in schema.tables:
        if table.name not in frames:
            continue
        raw_frame = frames[table.name]
        if raw_frame.shape[0] == 0:
            print(f"  {table.name}: empty — skipping cast test")
            continue
        typed = table.cast_frame(raw_frame)   # type-only cast, no Enum enforcement
        assert typed.shape == raw_frame.shape
        print(f"  {table.name}: cast OK, {typed.shape}")


@pytest.mark.integration
@pytest.mark.xfail(reason="POST /dataset/exportFile returned 403 — requires additional permissions")
def test_export_file_single_table(df_1619):
    handle = df_1619.export_file(
        dataset_id=DATASET_ID,
        table_schema_id=TABLE_SCHEMA_ID,
        mime_type="csv",
    )
    csv_bytes = handle.result(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  export_file status: {s}"),
    )
    assert isinstance(csv_bytes, bytes)
    print(f"  export_file: {len(csv_bytes)} bytes")


@pytest.mark.integration
@pytest.mark.xfail(reason="GET /dataset/exportDatasetFile returned 404 — endpoint not available")
def test_export_dataset_file_csv(df_1619):
    handle = df_1619.export_dataset_file(dataset_id=DATASET_ID, mime_type="csv")
    result = handle.result(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  export_dataset_file status: {s}"),
    )
    assert len(result) > 0
    print(f"  export_dataset_file: {len(result)} bytes")


@pytest.mark.integration
@pytest.mark.xfail(
    reason="/dataset/exportDatasetFileDL returned 404 on live API — endpoint may not be deployed"
)
def test_export_dataset_file_dl(df_1619):
    handle = df_1619.export_dataset_file_dl(dataset_id=DATASET_ID)
    zip_bytes = handle.result(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  export_dataset_file_dl status: {s}"),
    )
    assert len(zip_bytes) > 0


# ── Validation ────────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_list_group_validations_dl(df_1619):
    """Check raw response shape — printed output helps build ValidationResult parser."""
    results = df_1619.list_group_validations_dl(dataset_id=DATASET_ID)
    assert isinstance(results, dict)
    print(f"\n  keys: {list(results.keys())}")
    # Print first validation entry to understand the schema
    for key in ("validations", "errors", "groupValidations"):
        if key in results and isinstance(results[key], list) and results[key]:
            print(f"  {key}[0]: {results[key][0]}")
            break


@pytest.mark.integration
def test_validate_convenience(df_1619):
    """validate() triggers job + waits + returns structured ValidationResult."""
    from reportnet import DatasetLockedError, ValidationResult

    try:
        result = df_1619.validate(
            dataset_id=DATASET_ID,
            poll_interval=10.0,
            timeout=600.0,
            on_status=lambda s: print(f"  validation status: {s}"),
        )
    except DatasetLockedError as e:
        pytest.skip(f"Dataset locked — another job is already running: {e}")

    assert isinstance(result, ValidationResult)
    assert result.dataset_id == DATASET_ID
    assert isinstance(result.issues, list)
    assert isinstance(result.raw, dict)
    print(f"\n  {result.summary()}")
    if result.issues:
        print(f"  first issue: {result.issues[0]}")
        frame = result.to_frame()
        print(f"  to_frame(): {frame.shape}")


@pytest.mark.integration
def test_validation_job_and_results(df_1619):
    """Low-level: add_validation_job + wait + list_group_validations_dl."""
    from reportnet import DatasetLockedError

    try:
        handle = df_1619.add_validation_job(dataset_id=DATASET_ID)
    except DatasetLockedError as e:
        pytest.skip(f"Dataset locked — another job is already running: {e}")

    from reportnet.exceptions import JobTimeoutError

    try:
        handle.wait(
            poll_interval=10.0,
            timeout=600.0,
            on_status=lambda s: print(f"  validation job status: {s}"),
        )
    except JobTimeoutError:
        pytest.skip("Validation job still running after 600 s — server-side slowness")
    results = df_1619.list_group_validations_dl(dataset_id=DATASET_ID)
    assert isinstance(results, dict)


# ── Dataset management ────────────────────────────────────────────────────────

@pytest.mark.integration
def test_check_import_process(df_1619):
    status = df_1619.check_import_process(dataset_id=DATASET_ID)
    assert "anyLockAssigned" in status or isinstance(status, dict)
    print(f"\n  import process status: {status}")


@pytest.mark.integration
@pytest.mark.xfail(
    reason="GET /snapshot/v1/historicReleases returned 403 — requires custodian access"
)
def test_list_historic_releases(df_1619):
    releases = df_1619.list_historic_releases(dataset_id=DATASET_ID)
    assert isinstance(releases, list)
    print(f"\n  {len(releases)} historic release(s)")
    for r in releases[:3]:
        print(f"    {r}")


# ── Import test ────────────────────────────────────────────────────────────────

def _generate_csv() -> bytes:
    """Generate two rows of plausible Table1a data with pipe delimiter."""
    rows = [
        "category|scenario|ry|cyear|gas|cvalue|notation|inventorySubmissionYear",
        "Total including LULUCF|WEM|0|2024|Total GHG emissions (ktCO2e)|1111|NA|2024",
        "Total excluding LULUCF|WEM|0|2024|CO2 (ktCO2e)|2222|NA|2024",
    ]
    return "\n".join(rows).encode()


@pytest.mark.integration
def test_import_file_csv(df_1619):
    """Upload generated rows as CSV (append, does not replace existing data)."""
    from reportnet import DatasetLockedError

    csv_bytes = _generate_csv()
    print(f"\n  uploading:\n{csv_bytes.decode()}")

    try:
            handle = df_1619.import_file(
            dataset_id=DATASET_ID,
            file=csv_bytes,
            filename="test_upload.csv",
            table_schema_id=TABLE_SCHEMA_ID,
            replace=False,
        )
    except DatasetLockedError as e:
        pytest.skip(f"Dataset locked — another job is still running: {e}")
    handle.wait(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  import status: {s}"),
    )

    frames = df_1619.etl_export(dataset_id=DATASET_ID).to_frames(
        poll_interval=10.0,
        timeout=600.0,
    )
    assert "Table1a" in frames
    print(f"  Table1a now has {frames['Table1a'].shape[0]} rows")


@pytest.mark.integration
def test_import_file_dataframe(df_1619):
    """Upload a polars DataFrame — verifies the delimiter fix."""
    from reportnet import DatasetLockedError

    pl = pytest.importorskip("polars")

    df = pl.DataFrame({
        "category":                ["Total including LULUCF"],
        "scenario":                ["WEM"],
        "ry":                      ["0"],
        "cyear":                   [2024],
        "gas":                     ["Total GHG emissions (ktCO2e)"],
        "cvalue":                  [9999.0],
        "notation":                ["NA"],
        "inventorySubmissionYear": [2024],
    })
    print(f"\n  uploading DataFrame:\n{df}")

    try:
        handle = df_1619.import_file(
            dataset_id=DATASET_ID,
            file=df,
            filename="test_df_upload.csv",
            table_schema_id=TABLE_SCHEMA_ID,
            replace=False,
        )
    except DatasetLockedError as e:
        pytest.skip(f"Dataset locked — another job is still running: {e}")
    handle.wait(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  import status: {s}"),
    )

    frames = df_1619.etl_export(dataset_id=DATASET_ID).to_frames(
        poll_interval=10.0,
        timeout=600.0,
    )
    assert "Table1a" in frames
    print(f"  Table1a now has {frames['Table1a'].shape[0]} rows")


@pytest.mark.integration
def test_import_frames_dict(df_1619):
    """import_frames() uploads a dict of DataFrames, one per table."""
    from reportnet import DatasetLockedError

    pl = pytest.importorskip("polars")

    frames = {
        "Table1a": pl.DataFrame({
            "category":                ["Total including LULUCF"],
            "scenario":                ["WEM"],
            "ry":                      ["0"],
            "cyear":                   [2024],
            "gas":                     ["Total GHG emissions (ktCO2e)"],
            "cvalue":                  [42.0],
            "notation":                ["NA"],
            "inventorySubmissionYear": [2024],
        }),
    }
    print(f"\n  import_frames: {list(frames)} → {list(frames.values())[0].shape}")

    try:
        df_1619.import_frames(
            dataset_id=DATASET_ID,
            frames=frames,
            replace=False,
            poll_interval=10.0,
            timeout=600.0,
        )
    except DatasetLockedError as e:
        pytest.skip(f"Dataset locked — another job is still running: {e}")

    exported = df_1619.etl_export(dataset_id=DATASET_ID).to_frames(
        poll_interval=10.0,
        timeout=600.0,
    )
    assert "Table1a" in exported
    print(f"  Table1a after import_frames: {exported['Table1a'].shape[0]} rows")


# ── Visualisation ──────────────────────────────────────────────────────────────

@pytest.mark.integration
def test_to_mermaid(df_1619):
    mmd = df_1619.to_mermaid()
    assert mmd.startswith("graph LR")
    assert 'df[["' in mmd                  # dataflow node
    assert "subgraph cluster_" in mmd      # at least one reporter cluster
    print(f"\n  Mermaid length: {len(mmd)} chars")


@pytest.mark.integration
def test_to_mermaid_include_test(df_1619):
    mmd = df_1619.to_mermaid(include_test=True)
    assert "graph LR" in mmd
    print(f"\n  Mermaid with test datasets: {len(mmd)} chars")
