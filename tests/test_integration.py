"""Live integration tests against the real Reportnet API.

Run with:
    uv run pytest --integration -v

The --integration FLAG is what enables these; `-m integration` alone selects
them and conftest then skips every one, so that command reports success having
run nothing. To run a subset, combine the two:
    uv run pytest --integration -m integration -k bigdata -v

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
def test_is_big_dataflow(df_1619):
    """`assert isinstance(is_big, bool)` passed whatever the answer was, so it
    could never fail. Assert the invariant instead: the cached flag, the raw
    payload field, and the etlExport version the client auto-selects must all
    agree. Those three disagreeing is the actual bug worth catching — it sends
    the wrong export version and silently changes the payload shape."""
    is_big = df_1619.is_big_dataflow()
    assert isinstance(is_big, bool)
    assert is_big is df_1619.get_dataflow_contents().info.big_data

    handle = df_1619.etl_export(dataset_id=DATASET_ID)
    expected_version = "v4" if is_big else "v3"
    print(f"\n  BigData={is_big}, export kicked off as {expected_version}")
    assert handle.job_id


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


# ── BigData dataflow (2003) — reporter-scoped v4 export / import ────────────────
# Regression coverage for a bug where v4/v5 etlExport and importFileData both
# 403'd whenever providerId was included, which DataflowClient auto-injected
# for any reporter-scoped client (for_provider / find_reporter). See
# dataflow.py etl_export() / import_file().

DATAFLOW_ID_BIGDATA = 2003


@pytest.fixture(scope="module")
def client_2003():
    try:
        key = reportnet.get_key(DATAFLOW_ID_BIGDATA)
    except KeyError:
        pytest.skip(f"No API key in keyring for dataflow {DATAFLOW_ID_BIGDATA}")
    return reportnet.ReportnetClient(api_key=key)


@pytest.fixture(scope="module")
def df_2003(client_2003):
    return client_2003.for_dataflow(DATAFLOW_ID_BIGDATA)


@pytest.mark.integration
def test_is_big_dataflow_2003(df_2003):
    assert df_2003.is_big_dataflow() is True


@pytest.mark.integration
def test_etl_export_v4_scoped_reporter_no_403(df_2003):
    """v4 etlExport must not auto-inject providerId for a reporter-scoped
    DataflowClient — the API 403s if it does, even when the id matches the
    dataset's actual owner. Only checks kickoff + first poll (not full
    completion) since job processing time isn't part of what's regression-
    tested here."""
    reporters = df_2003.get_reporters()
    assert reporters, "no reporters in dataflow"
    pid = reporters[0].provider_id
    scoped = df_2003.for_provider(pid)
    datasets = scoped.get_reporting_datasets()
    assert datasets, "no reporting datasets for this provider"

    handle = scoped.etl_export(dataset_id=datasets[0].id)
    status = handle.status()
    print(f"\n  provider_id={pid} dataset={datasets[0].id} status={status}")


@pytest.mark.integration
def test_import_file_v2_scoped_reporter_no_403(df_2003):
    """import_file() must not auto-inject providerId for a reporter-scoped
    DataflowClient on a BigData dataflow — same root cause as the etlExport
    403 above. Targets a Test Dataset (not the reporting dataset) since the
    reporting dataset in this dataflow is PENDING and rejects all imports
    regardless of providerId.

    Only asserts the request is accepted (no AuthError/APIError) — the job
    itself may still end CANCELED with "Import is not allowed for this
    dataset" while dataflow 2003 remains in DRAFT status; that's a dataflow
    lifecycle gate on the server, not something this client can control.
    """
    test_datasets = df_2003.get_test_datasets()
    descriptive = [t for t in test_datasets if "Descriptive" in t.name]
    assert descriptive, f"no descriptive test dataset in {test_datasets}"

    reporters = df_2003.get_reporters()
    assert reporters, "no reporters in dataflow"
    scoped = df_2003.for_provider(reporters[0].provider_id)

    csv_body = (
        "repCode|conName|conInstitution|conStreet|conZIP|conCity|"
        "conPhone|conEmail|conRemarks\n"
        "TEST|Integration Test|reportnet-client|||test-phone|"
        "test@example.com|synthetic regression-test row\n"
    ).encode()
    handle = scoped.import_file(
        dataset_id=descriptive[0].id,
        file=csv_body,
        filename="contacts.csv",
        table_schema_id=descriptive[0].schema_id,
    )
    status = handle.status()
    print(f"\n  dataset={descriptive[0].id} status={status}")


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
    # `or isinstance(status, dict)` used to make this unfailable — status is
    # always a dict. Assert on the payload the client actually depends on.
    assert isinstance(status, dict)
    assert "importInProgress" in status or "anyLockAssigned" in status, status
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
    assert 'df[["' in mmd           # dataflow node
    assert "\n    p_" in mmd        # at least one reporter node (one per provider)
    print(f"\n  Mermaid length: {len(mmd)} chars")


@pytest.mark.integration
def test_to_mermaid_include_test(df_1619):
    mmd = df_1619.to_mermaid(include_test=True)
    assert "graph LR" in mmd
    print(f"\n  Mermaid with test datasets: {len(mmd)} chars")


# ── Reference-dataset selection, coverage reporting, name lookup, logging ──────
# These cover the reliability work: get_template() used to blindly take refs[0],
# which is wrong on dataflow 2003 (the codelists are NOT the first reference
# dataset). All read-only — no imports, no deletes.

@pytest.mark.integration
def test_reference_dataset_selection_beats_refs_zero(df_2003):
    """The schema-based picker must choose a reference dataset that actually
    covers the reporting dataset's LINK fields — which on this dataflow is not
    refs[0]. Schema-only, so no export jobs are started."""
    from reportnet._util import linked_field_names, reference_coverage

    reporters = df_2003.get_reporters()
    scoped = df_2003.for_provider(reporters[0].provider_id)
    datasets = scoped.get_reporting_datasets()
    assert datasets, "no reporting datasets for this provider"

    refs = df_2003.get_reference_datasets()
    if not refs:
        pytest.skip("dataflow has no reference datasets")

    # Find a dataset that actually has LINK fields to resolve.
    target = None
    for ds in datasets:
        schema = scoped.get_schema(dataset_id=ds.id)
        if linked_field_names(schema):
            target = (ds, schema)
            break
    if target is None:
        pytest.skip("no LINK/CODELIST fields in this provider's datasets")
    ds, schema = target

    linked = linked_field_names(schema)
    coverage = {}
    for ref in refs:
        try:
            coverage[ref.id] = reference_coverage(schema, scoped.get_schema(dataset_id=ref.id))
        except reportnet.ReportnetError as exc:
            print(f"    ref {ref.id}: schema unreadable ({exc})")

    print(f"\n  dataset {ds.id} ({ds.table_name}) has {len(linked)} LINK field(s)")
    for ref in refs:
        print(f"    ref {ref.id:>6}  {ref.name[:45]:<45} covers {coverage.get(ref.id, '?')}")

    chosen = scoped._best_reference_dataset(schema, refs)
    assert chosen is not None, f"no reference dataset covers {linked}"
    assert coverage[chosen.id] == max(coverage.values())
    print(f"  -> selected {chosen.id} ({chosen.name}), covering {coverage[chosen.id]}")

    # The whole point: blindly taking refs[0] would have been worse here.
    if coverage.get(refs[0].id, 0) < coverage[chosen.id]:
        print(f"  refs[0] would have covered only {coverage.get(refs[0].id, 0)} — "
              f"this is the bug the picker fixes")


@pytest.mark.integration
def test_get_template_reports_coverage_and_types_link_columns(df_2003):
    """End-to-end on real data: get_template() should either produce Enum
    columns or warn — never silently hand back unconstrained strings."""
    import warnings

    pytest.importorskip("polars")
    import polars as pl

    from reportnet._util import linked_field_names

    reporters = df_2003.get_reporters()
    scoped = df_2003.for_provider(reporters[0].provider_id)
    datasets = scoped.get_reporting_datasets()

    target = None
    for ds in datasets:
        if linked_field_names(scoped.get_schema(dataset_id=ds.id)):
            target = ds
            break
    if target is None:
        pytest.skip("no LINK/CODELIST fields in this provider's datasets")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        templates = scoped.get_template(dataset_id=target.id, poll_interval=5.0, timeout=600.0)

    linked = set(linked_field_names(scoped.get_schema(dataset_id=target.id)))
    enum_cols, string_cols = [], []
    for name, frame in templates.items():
        for col, dtype in frame.schema.items():
            if col in linked:
                (enum_cols if isinstance(dtype, pl.Enum) else string_cols).append(f"{name}.{col}")

    print(f"\n  dataset {target.id} ({target.table_name})")
    print(f"    Enum-typed LINK columns:   {enum_cols}")
    print(f"    plain-string LINK columns: {string_cols}")
    for w in caught:
        print(f"    warning: {w.message}")

    # The contract: any LINK column left unconstrained must have been warned about.
    if string_cols:
        assert caught, f"{string_cols} fell back to plain strings with no warning"


@pytest.mark.integration
def test_dataset_lookup_by_table_name(df_2003):
    """Name-based lookup should agree with positional access, without the guessing."""
    reporters = df_2003.get_reporters()
    scoped = df_2003.for_provider(reporters[0].provider_id)
    datasets = scoped.get_reporting_datasets()
    assert datasets, "no reporting datasets for this provider"

    by_table = scoped.datasets_by_table()
    print(f"\n  {len(by_table)} table(s): {sorted(by_table)}")

    first = datasets[0]
    assert scoped.dataset(first.table_name).id == first.id
    assert scoped.dataset(first.table_name.lower()).id == first.id

    with pytest.raises(KeyError) as excinfo:
        scoped.dataset("DefinitelyNotATable")
    assert first.table_name in str(excinfo.value)


@pytest.mark.integration
def test_reference_dataset_lookup_by_name(df_2003):
    refs = df_2003.get_reference_datasets()
    if not refs:
        pytest.skip("dataflow has no reference datasets")
    print(f"\n  reference datasets: {[r.name for r in refs]}")
    assert df_2003.reference_dataset(refs[0].name).id == refs[0].id


@pytest.mark.integration
def test_get_dataflow_contents_is_one_request(df_2003, caplog):
    """All four getters read the same endpoint; contents must fetch it once."""
    import logging as _logging

    with caplog.at_level(_logging.DEBUG, logger="reportnet"):
        contents = df_2003.get_dataflow_contents()

    requests = [r.getMessage() for r in caplog.records if "/dataflow/v1/" in r.getMessage()]
    # One debug line for the request, one for the response.
    assert len([r for r in requests if "->" not in r]) == 1, requests
    print(f"\n  {contents.info.name}: {len(contents.reporting_datasets)} reporting, "
          f"{len(contents.reference_datasets)} reference, "
          f"{len(contents.test_datasets)} test dataset(s)")


@pytest.mark.integration
def test_live_requests_are_logged(df_2003, caplog):
    import logging as _logging

    with caplog.at_level(_logging.DEBUG, logger="reportnet"):
        df_2003.get_dataflow()

    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("GET ") for m in messages), messages
    assert not any("ApiKey" in m for m in messages), "API key must never be logged"


# ── Cross-backend behaviour ───────────────────────────────────────────────────
# Everything above is written against one dataflow at a time, so a method that
# is wrong for a whole backend passes unnoticed — which is exactly how
# validate() came to call the BigData listing endpoint on every dataflow.
# These run the same behaviour against both dataflows.

BACKEND_DATAFLOWS = [
    pytest.param(DATAFLOW_ID, id=f"df{DATAFLOW_ID}"),
    pytest.param(DATAFLOW_ID_BIGDATA, id=f"df{DATAFLOW_ID_BIGDATA}"),
]


@pytest.fixture(scope="module", params=BACKEND_DATAFLOWS)
def any_backend(request):
    """A DataflowClient per configured dataflow, whatever its backend.

    Distinguishes "no key configured" from "key lacks rights": the first is a
    setup gap, the second is a finding. Reporting both as a bare skip hides
    permission problems behind what looks like an unconfigured machine.
    """
    dataflow_id = request.param
    try:
        key = reportnet.get_key(dataflow_id)
    except KeyError:
        pytest.skip(f"No API key in keyring for dataflow {dataflow_id}")

    flow = reportnet.ReportnetClient(api_key=key).for_dataflow(dataflow_id)
    try:
        flow.get_dataflow()
    except reportnet.AuthError as exc:
        pytest.skip(
            f"key for dataflow {dataflow_id} cannot read GET /dataflow/v1/{dataflow_id} "
            f"({exc}) — reporter-scoped keys hit this; grant read rights to run "
            f"the cross-backend tests"
        )
    return flow


def _first_reporting_dataset(flow):
    datasets = flow.get_reporting_datasets()
    if not datasets:
        pytest.skip("dataflow has no reporting datasets")
    return datasets[0]


@pytest.mark.integration
def test_validation_listing_endpoint_matches_backend(any_backend):
    """listGroupValidations (Citus) and listGroupValidationsDL (BigData) are not
    interchangeable. The endpoint matching this dataflow's backend must work.

    validate() chose DL unconditionally, so on a Citus dataflow it read the
    wrong endpoint — invisible while only one backend was ever exercised.
    """
    dataset = _first_reporting_dataset(any_backend)
    is_big = any_backend.is_big_dataflow()
    call = (
        any_backend.list_group_validations_dl
        if is_big
        else any_backend.list_group_validations
    )
    try:
        results = call(dataset_id=dataset.id)
    except reportnet.AuthError as exc:
        pytest.skip(f"validation listing not authorised for this key: {exc}")

    assert isinstance(results, dict)
    print(f"\n  BigData={is_big} -> {'DL' if is_big else 'non-DL'} endpoint, "
          f"keys: {list(results)}")


@pytest.mark.integration
def test_etl_export_auto_selects_the_version_for_this_backend(any_backend):
    """v4 for BigData, v3 for Citus. Sending the wrong one mostly 'succeeds'
    but returns a differently-shaped payload, which is why the version is
    looked up rather than guessed."""
    dataset = _first_reporting_dataset(any_backend)
    is_big = any_backend.is_big_dataflow()

    handle = any_backend.etl_export(dataset_id=dataset.id)
    assert handle.job_id, "export job was not created"
    print(f"\n  BigData={is_big} -> job {handle.job_id} "
          f"(expects v{'4' if is_big else '3'})")


@pytest.mark.integration
def test_finished_export_actually_returns_the_tables(any_backend):
    """A terminal job status is not evidence that data moved.

    Reportnet reports jobs FINISHED that produced nothing (etlImport does this
    for records missing countryCode), so any test that asserts only on
    .status() can pass while the operation did nothing. This one reads the
    payload back.
    """
    dataset = _first_reporting_dataset(any_backend)
    try:
        frames = any_backend.etl_export(dataset_id=dataset.id).to_frames(
            poll_interval=10.0, timeout=1800.0
        )
    except reportnet.JobTimeoutError:
        pytest.skip("export job did not finish within 30 min — server-side queueing")

    assert isinstance(frames, dict)
    assert frames, "a FINISHED export returned no tables at all"
    for name, frame in frames.items():
        print(f"    {name}: {frame.shape}")
    schema = any_backend.get_schema(dataset_id=dataset.id)
    known = {t.name for t in schema.tables}
    unexpected = set(frames) - known
    assert not unexpected, f"export returned tables absent from the schema: {unexpected}"
