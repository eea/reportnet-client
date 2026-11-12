"""Live schema-design cycle on the Reportnet 3 **sandbox**, dataflow 11468.

Run with:
    RN3_SANDBOX_ACCESS_TOKEN=... RN3_SANDBOX_REFRESH_TOKEN=... \\
        uv run pytest --integration -m integration -k schema_design -v

Copy both tokens from the web app while logged in to the sandbox: DevTools →
Application → Session storage → ``reportnet_03``. Skipped if they are missing.

**This writes to a shared sandbox.** Each run creates one new design dataset
named ``rnclient-it-<timestamp>``. Reportnet has no verified API call to delete
a whole design dataset yet, so the test empties it but leaves it in place:
delete old ``rnclient-it-`` datasets in the web app now and then.

Design datasets 33796 ("Reference data", holds data) and 33797 ("Reporting
data") are never touched.
"""

import csv
import io
import os
import time

import pytest

import reportnet
from reportnet.exceptions import AuthError, SchemaDesignNotPermittedError

DATAFLOW_ID = 11468
PROTECTED = {33796, 33797}
PREFIX = "rnclient-it-"


@pytest.fixture(scope="module")
def token_client():
    access = os.environ.get("RN3_SANDBOX_ACCESS_TOKEN")
    refresh = os.environ.get("RN3_SANDBOX_REFRESH_TOKEN")
    if not (access and refresh):
        pytest.skip("RN3_SANDBOX_ACCESS_TOKEN / RN3_SANDBOX_REFRESH_TOKEN not set")
    return reportnet.ReportnetClient.from_tokens(access, refresh, sandbox=True)


@pytest.fixture(scope="module")
def scratch(token_client):
    flow = token_client.for_dataflow(DATAFLOW_ID)
    ds = flow.create_design_dataset(f"{PREFIX}{time.strftime('%Y%m%d-%H%M%S')}")
    assert ds.id not in PROTECTED
    print(f"\n  scratch design dataset {ds.id} {ds.name!r} ({ds.schema_id})")
    return flow, ds


@pytest.mark.integration
def test_schema_design_full_cycle(scratch):
    flow, ds = scratch
    designer = flow.design(ds.id)

    assert designer.set_description("rnclient integration test").description

    sites = designer.add_table("Sites", mandatory=True, description="sites")
    assert sites.record_id, "create_table_schema must return the record schema id"
    code = designer.add_field(sites, "SiteCode", "TEXT", pk=True, required=True,
                              description="Site code")
    area = designer.add_field(sites, "Area", "NUMBER_DECIMAL", description="Area km2")
    status = designer.add_field(sites, "Status", "CODELIST", codelist=["open", "closed"],
                                description="site status")
    assert status.codelist_items == ("open", "closed")

    meas = designer.add_table("Measurements")
    link = designer.add_field(meas, "Site", "LINK", required=True, link_to=code)
    assert link.referenced_pk_id == code.id
    assert designer.field(code).pk_referenced is True

    # Known risk: a LINK update sends back referencedField as read, including
    # keys GET adds (labelId, tableSchemaName, ...). Not captured from the web
    # app; if this fails, report the error text — do not work around it.
    link = designer.update_field(link, description="link to Sites")
    assert link.referenced_pk_id == code.id

    # Full-body update: a partial body answered 500 here on 2026-11-12.
    updated = designer.update_field(area, description="helloworld")
    assert updated.description == "helloworld"
    assert updated.type == reportnet.FieldType.NUMBER_DECIMAL

    order = [f.name for f in designer.move_field(status, 0).fields]
    assert order == ["Status", "SiteCode", "Area"]
    assert [t.name for t in designer.move_table(meas, 0).tables] == ["Measurements", "Sites"]

    rows = list(csv.DictReader(io.StringIO(designer.export_table_definition(sites))))
    assert [r["Field name"] for r in rows] == ["Status", "SiteCode", "Area"]
    by_name = {r["Field name"]: r for r in rows}
    assert by_name["SiteCode"]["PK"] == "true"
    assert by_name["Status"]["Extra information"] == "open;closed"
    assert by_name["Area"]["Field description"] == "helloworld"

    # Schema changes create automatic QC rules; read them as evidence only.
    rules = flow._client._http.get(f"/rules/{ds.schema_id}/dataflow/{DATAFLOW_ID}").json()
    print(f"  automatic rules after the build: {len(rules.get('rules') or [])}")

    designer.delete_field(link)
    designer.delete_table(meas)
    designer.delete_table(sites)
    assert designer.schema().tables == ()


@pytest.mark.integration
def test_api_key_is_refused_schema_reads():
    """If this starts passing the read, Reportnet has changed: revisit the
    login-token requirement (brief §2.1, 2026-11-12)."""
    try:
        key = reportnet.get_key(DATAFLOW_ID, sandbox=True)
    except (KeyError, ImportError):
        pytest.skip(f"No sandbox API key in keyring for dataflow {DATAFLOW_ID}")
    client = reportnet.ReportnetClient(api_key=key, base_url=reportnet.SANDBOX_URL)
    with pytest.raises(AuthError) as exc:
        client._http.get(f"/dataschema/getSchemas/dataflow/{DATAFLOW_ID}")  # read-only probe
    assert exc.value.status_code in (401, 403, 500)
    with pytest.raises(SchemaDesignNotPermittedError):
        client.list_schemas(dataflow_id=DATAFLOW_ID)
