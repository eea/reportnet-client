"""SchemaDesigner (WP5): guards, read-modify-write and read-back.

A small in-memory fake of the schema service stands in for Reportnet, so each
test sees writes reflected in the next read — the read-back is real.
"""

import base64
import itertools
import json
import time

import httpx
import pytest

from reportnet import ReportnetClient
from reportnet.exceptions import (
    DuplicateNameError,
    SchemaDesignError,
    SchemaDesignNotPermittedError,
    SchemaReadbackError,
    TableHasDataError,
)

FLOW, DS, SCHEMA = 11468, 48097, "6af5bb2fc6dc4400014d1f2a"


def _jwt() -> str:
    def enc(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{enc({'alg': 'none'})}.{enc({'exp': int(time.time()) + 3600})}.s"


class FakeSchemaService:
    """Just enough of /dataschema to make read-back meaningful."""

    def __init__(self, router, *, big_data=True, data_collections=()):
        self.ids = (f"id{n:04d}" for n in itertools.count())
        self.records: dict[str, int] = {}
        self.design = [{"id": DS, "dataSetName": "Scratch", "datasetSchema": SCHEMA}]
        self.contents = {"id": FLOW, "name": "F", "bigData": big_data,
                         "dataCollections": list(data_collections),
                         "designDatasets": self.design}
        self.schema = {"idDataSetSchema": SCHEMA, "nameDatasetSchema": "Scratch",
                       "description": None, "tableSchemas": []}
        self.drop_next_field_change = False   # simulate a write that did not land
        r = router
        r.get(f"/dataflow/v1/{FLOW}").mock(side_effect=lambda req: httpx.Response(
            200, json=self.contents))
        r.get(f"/dataschema/v1/datasetId/{DS}").mock(side_effect=lambda req: httpx.Response(
            200, json=self.schema))
        self.create_dataset_route = r.post("/dataschema/createEmptyDatasetSchema").mock(
            side_effect=self.create_dataset)
        r.put("/datasetmetabase/updateDatasetName").mock(side_effect=self.rename)
        r.put(f"/dataschema/{DS}/datasetSchema").mock(side_effect=self.describe)
        self.create_table_route = r.post(f"/dataschema/{DS}/tableSchema").mock(
            side_effect=self.create_table)
        self.update_table_route = r.put(f"/dataschema/{DS}/tableSchema").mock(
            side_effect=self.update_table)
        r.put(f"/dataschema/{DS}/tableSchema/order").mock(side_effect=self.order_table)
        r.delete(url__regex=rf"/dataschema/{DS}/tableSchema/(?P<tid>\w+)$").mock(
            side_effect=self.delete_table)
        self.create_field_route = r.post(f"/dataschema/{DS}/fieldSchema").mock(
            side_effect=self.create_field)
        self.update_field_route = r.put(f"/dataschema/{DS}/fieldSchema").mock(
            side_effect=self.update_field)
        r.put(f"/dataschema/{DS}/fieldSchema/order").mock(side_effect=self.order_field)
        self.delete_field_route = r.delete(
            url__regex=rf"/dataschema/{DS}/fieldSchema/(?P<fid>\w+)$").mock(
            side_effect=self.delete_field)
        self.count_route = r.get(f"/dataset/TableValueDatasetDL/{DS}").mock(
            side_effect=lambda req: httpx.Response(200, json={
                "totalRecords": self.records.get(req.url.params["idTableSchema"], 0)}))
        r.get(f"/dataset/getImportRelatedStatistics/{DS}").mock(
            side_effect=lambda req: httpx.Response(200, json={
                tid: {"numberOfRecordsImported": n} for tid, n in self.records.items()}))

    # helpers
    def tables(self):
        return self.schema["tableSchemas"]

    def all_fields(self):
        for t in self.tables():
            for f in t["recordSchema"]["fieldSchema"] or []:
                yield t, f

    # handlers
    def create_dataset(self, req):
        name = req.url.params["datasetSchemaName"]
        self.design.append({"id": 50000 + len(self.design), "dataSetName": name,
                            "datasetSchema": next(self.ids)})
        return httpx.Response(200)

    def rename(self, req):
        self.schema["nameDatasetSchema"] = req.url.params["datasetName"]
        return httpx.Response(200)

    def describe(self, req):
        self.schema["description"] = json.loads(req.content)["description"]
        return httpx.Response(200)

    def create_table(self, req):
        b = json.loads(req.content)
        t = {"idTableSchema": next(self.ids), "nameTableSchema": b["nameTableSchema"],
             "description": None, "notEmpty": b.get("notEmpty", False), "readOnly": False,
             "toPrefill": False, "fixedNumber": False, "dataAreManuallyEditable": False,
             "recordSchema": {"idRecordSchema": next(self.ids), "fieldSchema": None}}
        self.tables().append(t)
        return httpx.Response(200, json=t)

    def update_table(self, req):
        b = json.loads(req.content)
        t = next(t for t in self.tables() if t["idTableSchema"] == b["idTableSchema"])
        t.update({k: v for k, v in b.items() if k != "idTableSchema"})
        return httpx.Response(200)

    def order_table(self, req):
        b = json.loads(req.content)
        t = next(t for t in self.tables() if t["idTableSchema"] == b["id"])
        self.tables().remove(t)
        self.tables().insert(b["position"], t)
        return httpx.Response(200)

    def delete_table(self, req, tid):
        self.schema["tableSchemas"] = [t for t in self.tables() if t["idTableSchema"] != tid]
        return httpx.Response(200)

    def create_field(self, req):
        b = json.loads(req.content)
        t = next(t for t in self.tables()
                 if t["recordSchema"]["idRecordSchema"] == b["idRecord"])
        f = {**b, "id": next(self.ids), "pkReferenced": False, "pkMustBeUsed": False}
        if f.get("referencedField"):
            f["referencedField"] = {**f["referencedField"], "labelId": None}
            for _, pkf in self.all_fields():
                if pkf["id"] == f["referencedField"]["idPk"]:
                    pkf["pkReferenced"] = True
        t["recordSchema"]["fieldSchema"] = (t["recordSchema"]["fieldSchema"] or []) + [f]
        return httpx.Response(200, text=f["id"], headers={"content-type": "text/plain"})

    def update_field(self, req):
        b = json.loads(req.content)
        if self.drop_next_field_change:
            self.drop_next_field_change = False
            return httpx.Response(200)
        for _, f in self.all_fields():
            if f["id"] == b["id"]:
                f.update(b)
        return httpx.Response(200)

    def order_field(self, req):
        b = json.loads(req.content)
        for t, f in list(self.all_fields()):
            if f["id"] == b["id"]:
                fields = t["recordSchema"]["fieldSchema"]
                fields.remove(f)
                fields.insert(b["position"], f)
                return httpx.Response(200)
        return httpx.Response(404)

    def delete_field(self, req, fid):
        for t in self.tables():
            t["recordSchema"]["fieldSchema"] = [
                f for f in t["recordSchema"]["fieldSchema"] or [] if f["id"] != fid]
        return httpx.Response(200)


@pytest.fixture
def service(mock_router):
    return FakeSchemaService(mock_router)


@pytest.fixture
def flow():
    return ReportnetClient.from_tokens(_jwt(), "rt").for_dataflow(FLOW)


@pytest.fixture
def designer(service, flow):
    return flow.design(DS)


# ── the brief's example, end to end ───────────────────────────────────────────

def test_brief_example_runs_end_to_end(service, flow):
    ds = flow.create_design_dataset("ClaudeApiTest")
    assert ds.name == "ClaudeApiTest"

    designer = flow.design(DS)
    sites = designer.add_table("Sites", mandatory=True)
    code = designer.add_field(sites, "SiteCode", "TEXT", pk=True, required=True)
    status = designer.add_field(sites, "Status", "CODELIST", codelist=["open", "closed"])
    assert status.codelist_items == ("open", "closed")

    updated = designer.update_field(code, description="helloworld")
    assert updated.description == "helloworld" and updated.pk is True

    table = designer.move_field(status, position=0)
    assert [f.name for f in table.fields] == ["Status", "SiteCode"]

    designer.delete_table(sites)
    assert designer.schema().tables == ()


# ── dataset level ─────────────────────────────────────────────────────────────

def test_create_design_dataset_refuses_an_existing_name(service, flow, mock_router):
    with pytest.raises(DuplicateNameError):
        flow.create_design_dataset("scratch")       # case-insensitive
    assert not service.create_dataset_route.called


def test_rename_and_description_are_read_back(designer, service):
    assert designer.rename("Renamed").name == "Renamed"
    assert designer.set_description("about").description == "about"


# ── guards ────────────────────────────────────────────────────────────────────

def test_api_key_client_cannot_open_a_designer(service):
    with pytest.raises(SchemaDesignNotPermittedError):
        ReportnetClient(api_key="k").for_dataflow(FLOW).design(DS)


def test_non_design_dataset_is_refused(service, flow):
    with pytest.raises(SchemaDesignError, match="not a design dataset"):
        flow.design(108953)


def test_schema_with_a_data_collection_is_refused_unless_allowed(mock_router, flow):
    FakeSchemaService(mock_router, data_collections=[{"id": 1, "datasetSchema": SCHEMA}])
    with pytest.raises(SchemaDesignError, match="reach reporters"):
        flow.design(DS)
    assert flow.design(DS, allow_after_data_collection=True).dataset_id == DS


def test_schema_with_reporting_datasets_is_refused(mock_router, flow):
    service = FakeSchemaService(mock_router)
    service.contents["reportingDatasets"] = [
        {"id": 7, "dataSetName": "IT", "datasetSchema": SCHEMA, "dataProviderId": 64}]
    with pytest.raises(SchemaDesignError, match="reach reporters"):
        flow.design(DS)


def test_data_collections_of_other_schemas_do_not_block(mock_router, flow):
    # Sandbox 11468 is a live reporting dataflow; a scratch dataset made today
    # has no copies even though the dataflow's other schemas do.
    FakeSchemaService(mock_router, data_collections=[{"id": 1, "datasetSchema": "other"}])
    assert flow.design(DS).dataset_id == DS


def test_table_with_data_is_locked_unless_forced(designer, service):
    sites = designer.add_table("Sites")
    code = designer.add_field(sites, "SiteCode", "TEXT")
    service.records[sites.id] = 3

    calls = service.update_field_route.call_count
    with pytest.raises(TableHasDataError, match="3 record"):
        designer.update_field(code, description="x")
    with pytest.raises(TableHasDataError):
        designer.add_field(sites, "Other", "TEXT")
    with pytest.raises(TableHasDataError):
        designer.delete_table(sites)
    assert service.update_field_route.call_count == calls     # nothing was sent

    assert designer.update_field(code, description="x", force=True).description == "x"
    assert service.update_field_route.call_count == calls + 1


def test_citus_dataflow_counts_from_import_statistics_and_warns(mock_router, flow):
    service = FakeSchemaService(mock_router, big_data=False)
    designer = flow.design(DS)
    with pytest.warns(UserWarning, match="last import"):
        sites = designer.add_table("Sites")
        service.records[sites.id] = 1
        with pytest.raises(TableHasDataError):
            designer.add_field(sites, "A", "TEXT")
    assert not service.count_route.called


def test_failed_data_check_refuses_rather_than_assuming_empty(designer, service, mock_router):
    sites = designer.add_table("Sites")
    mock_router.get(f"/dataset/TableValueDatasetDL/{DS}").mock(
        return_value=httpx.Response(400, text="idTableSchema missing"))
    with pytest.raises(SchemaDesignError, match="Could not check"):
        designer.add_field(sites, "A", "TEXT")


def test_duplicate_table_and_field_names_are_refused(designer, service):
    sites = designer.add_table("Sites")
    creates = service.create_table_route.call_count
    with pytest.raises(DuplicateNameError):
        designer.add_table("SITES")
    assert service.create_table_route.call_count == creates

    designer.add_field(sites, "Code", "TEXT")
    other = designer.add_field(sites, "Name", "TEXT")
    with pytest.raises(DuplicateNameError):
        designer.add_field(sites, "code", "TEXT")
    with pytest.raises(DuplicateNameError):
        designer.update_field(other, name="Code")
    designer.add_table("Measurements")
    with pytest.raises(DuplicateNameError):
        designer.update_table(sites, name="measurements")


# ── read-modify-write and read-back ───────────────────────────────────────────

def test_update_field_sends_the_whole_field_from_a_fresh_read(designer, service):
    sites = designer.add_table("Sites")
    stale = designer.add_field(sites, "Code", "TEXT", description="old")
    designer.update_field(stale, required=True)                # newer change
    designer.update_field(stale, description="new")            # stale object passed in

    sent = json.loads(service.update_field_route.calls.last.request.content)
    assert sent["required"] is True        # the newer change survived
    assert sent["description"] == "new"
    assert {"id", "idRecord", "name", "type", "codelistItems"} <= sent.keys()
    assert "pkReferenced" not in sent


def test_a_write_that_did_not_land_raises_readback_error(designer, service):
    sites = designer.add_table("Sites")
    code = designer.add_field(sites, "Code", "TEXT")
    service.drop_next_field_change = True
    with pytest.raises(SchemaReadbackError) as exc:
        designer.update_field(code, description="lost")
    assert exc.value.expected == {"description": "lost"}
    assert exc.value.actual == {"description": ""}


def test_add_table_with_properties_and_update(designer, service):
    t = designer.add_table("Sites", mandatory=True, description="d", read_only=True)
    assert (t.not_empty, t.description, t.read_only) == (True, "d", True)
    t = designer.update_table(t, name="Sites2", not_empty=False)
    assert (t.name, t.not_empty) == ("Sites2", False)


def test_move_table(designer, service):
    designer.add_table("A")
    b = designer.add_table("B")
    assert [t.name for t in designer.move_table(b, 0).tables] == ["B", "A"]


def test_link_field_to_a_primary_key_in_the_same_dataset(designer, service):
    sites = designer.add_table("Sites")
    code = designer.add_field(sites, "SiteCode", "TEXT", pk=True, required=True)
    meas = designer.add_table("Measurements")
    link = designer.add_field(meas, "Site", "LINK", required=True, link_to=code)
    sent = json.loads(service.create_field_route.calls.last.request.content)
    assert sent["referencedField"] == {"idDatasetSchema": SCHEMA, "idPk": code.id}
    assert link.referenced_pk_id == code.id
    assert designer.field(code).pk_referenced is True


def test_deleting_a_referenced_primary_key_warns(designer, service):
    sites = designer.add_table("Sites")
    code = designer.add_field(sites, "SiteCode", "TEXT", pk=True)
    designer.add_field(designer.add_table("M"), "Site", "LINK", link_to=code)
    with pytest.warns(UserWarning, match="primary key"):
        designer.delete_field(code)
    assert service.delete_field_route.called


def test_tables_are_found_by_name_id_or_object(designer, service):
    t = designer.add_table("Sites")
    assert designer.table("Sites").id == designer.table(t.id).id == designer.table(t).id
    with pytest.raises(KeyError):
        designer.table("Nope")


def test_export_table_definition(designer, service, mock_router):
    t = designer.add_table("Sites")
    mock_router.get(f"/dataschema/v1/{SCHEMA}/exportFieldSchemas").mock(
        return_value=httpx.Response(200, content=b"Field name,PK\n"))
    assert designer.export_table_definition("Sites") == "Field name,PK\n"
    assert designer.record_count(t) == 0
