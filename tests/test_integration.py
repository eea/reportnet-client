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

# ── Dataflow 1619 — BigData ────────────────────────────────────────────────
DATAFLOW_ID = 1619
DATASET_ID = 93953
# Custodian access — no provider_id required


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


# ── Export tests (read-only) ───────────────────────────────────────────────

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
@pytest.mark.xfail(reason="/dataset/exportDatasetFileDL returned 404 on live API — endpoint may not be deployed")
def test_export_dataset_file_dl(df_1619):
    """BigData whole-dataset datalake export."""
    handle = df_1619.export_dataset_file_dl(dataset_id=DATASET_ID)
    zip_bytes = handle.result(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  export_dataset_file_dl status: {s}"),
    )
    assert len(zip_bytes) > 0


@pytest.mark.integration
def test_list_group_validations_dl(df_1619):
    """Read validation results for the BigData dataset."""
    results = df_1619.list_group_validations_dl(dataset_id=DATASET_ID)
    assert isinstance(results, dict)
    print(f"  validation keys: {list(results)[:5]}")


@pytest.mark.integration
def test_validation_job_and_results(df_1619):
    """Trigger a validation job and wait for it to complete."""
    from reportnet import DatasetLockedError

    try:
        handle = df_1619.add_validation_job(dataset_id=DATASET_ID)
    except DatasetLockedError as e:
        pytest.skip(f"Dataset locked — another job is already running: {e}")

    handle.wait(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  validation job status: {s}"),
    )
    results = df_1619.list_group_validations_dl(dataset_id=DATASET_ID)
    assert isinstance(results, dict)


# ── Import test ────────────────────────────────────────────────────────────
# Table1a schema (derived from etl_export): 9 cols, comma-delimited.
# table_schema_id comes from the URL tab fragment.

TABLE_SCHEMA_ID = "68dd41f045f9450001260da7"


def _generate_csv() -> bytes:
    """Generate two rows of plausible Table1a data.

    record_id is omitted — Reportnet assigns it on ingestion.
    Pipe delimiter matches the API default.
    """
    rows = [
        "category|scenario|ry|cyear|gas|cvalue|notation|inventorySubmissionYear",
        "Total including LULUCF|WEM|0|2024|Total GHG emissions (ktCO2e)|1111|NA|2024",
        "Total excluding LULUCF|WEM|0|2024|CO2 (ktCO2e)|2222|NA|2024",
    ]
    return "\n".join(rows).encode()


@pytest.mark.integration
def test_import_file_bigdata(df_1619):
    """Upload generated rows to Table1a (append, does not replace existing data)."""
    csv_bytes = _generate_csv()
    print(f"\n  uploading:\n{csv_bytes.decode()}")

    handle = df_1619.import_file(
        dataset_id=DATASET_ID,
        file=csv_bytes,
        filename="test_upload.csv",
        table_schema_id=TABLE_SCHEMA_ID,
        # delimiter defaults to "|"
        replace=False,
    )
    handle.wait(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  import status: {s}"),
    )
    print("  import finished — verifying via export")

    frames = df_1619.etl_export(dataset_id=DATASET_ID).to_frames(
        poll_interval=10.0,
        timeout=600.0,
        on_status=lambda s: print(f"  export status: {s}"),
    )
    assert "Table1a" in frames
    print(f"  Table1a now has {frames['Table1a'].shape[0]} rows")
