"""Schema design endpoints (WP3). Request shapes are the ones captured from the
Reportnet web app on sandbox dataflow 11468, 2026-11-12."""

import base64
import json
import time

import httpx
import pytest

from reportnet import ReportnetClient
from reportnet.exceptions import (
    AuthError,
    SchemaDesignNotPermittedError,
    SchemaWriteUncertainError,
)

DS = 48097
SCHEMA_ID = "6af5bb2fc6dc4400014d1f2a"
TABLE_ID = "6af5b8cac6dc4400014d1f21"
RECORD_ID = "6af5b8cac6dc4400014d1f22"
FIELD_ID = "6af5b8f7c6dc4400014d1f25"


def _jwt() -> str:
    def enc(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{enc({'alg': 'none'})}.{enc({'exp': int(time.time()) + 3600})}.s"


@pytest.fixture
def token_client():
    return ReportnetClient.from_tokens(_jwt(), "rt")


def body(route) -> dict:
    return json.loads(route.calls.last.request.content)


def params(route) -> dict:
    return dict(route.calls.last.request.url.params)


def test_create_empty_dataset_schema(mock_router, token_client):
    route = mock_router.post("/dataschema/createEmptyDatasetSchema").mock(
        return_value=httpx.Response(200)
    )
    assert token_client.create_empty_dataset_schema(dataflow_id=11468, name="A B") is None
    assert params(route) == {"dataflowId": "11468", "datasetSchemaName": "A B"}


def test_update_dataset_name(mock_router, token_client):
    route = mock_router.put("/datasetmetabase/updateDatasetName").mock(
        return_value=httpx.Response(200)
    )
    token_client.update_dataset_name(dataset_id=DS, name="Renamed")
    assert params(route) == {"datasetId": str(DS), "datasetName": "Renamed"}


def test_update_dataset_schema_description(mock_router, token_client):
    route = mock_router.put(f"/dataschema/{DS}/datasetSchema").mock(
        return_value=httpx.Response(200)
    )
    token_client.update_dataset_schema(dataset_id=DS, description="desc")
    assert body(route) == {"description": "desc"}


def test_get_dataset_metabase(mock_router, token_client):
    mock_router.get(f"/datasetmetabase/{DS}").mock(
        return_value=httpx.Response(200, json={"id": DS, "dataSetName": "X"})
    )
    assert token_client.get_dataset_metabase(dataset_id=DS)["dataSetName"] == "X"


def test_create_table_schema_parses_the_returned_table(mock_router, token_client):
    route = mock_router.post(f"/dataschema/{DS}/tableSchema").mock(
        return_value=httpx.Response(200, json={
            "idTableSchema": TABLE_ID, "nameTableSchema": "ClaudeTable", "description": None,
            "notEmpty": True, "recordSchema": {"idRecordSchema": RECORD_ID, "fieldSchema": None},
        })
    )
    table = token_client.create_table_schema(dataset_id=DS, name="ClaudeTable", not_empty=True)
    assert body(route) == {"nameTableSchema": "ClaudeTable", "notEmpty": True}
    assert table.id == TABLE_ID
    assert table.fields == ()


def test_update_table_schema_maps_python_names_to_wire_names(mock_router, token_client):
    route = mock_router.put(f"/dataschema/{DS}/tableSchema").mock(return_value=httpx.Response(200))
    token_client.update_table_schema(
        dataset_id=DS, table_schema_id=TABLE_ID, description="d", fixed_number=False,
        not_empty=True, read_only=False, to_prefill=False, data_manually_editable=False,
    )
    assert body(route) == {
        "idTableSchema": TABLE_ID, "description": "d", "fixedNumber": False, "notEmpty": True,
        "readOnly": False, "toPrefill": False, "dataAreManuallyEditable": False,
    }


def test_update_table_schema_rename(mock_router, token_client):
    route = mock_router.put(f"/dataschema/{DS}/tableSchema").mock(return_value=httpx.Response(200))
    token_client.update_table_schema(dataset_id=DS, table_schema_id=TABLE_ID, name="T2")
    assert body(route) == {"idTableSchema": TABLE_ID, "nameTableSchema": "T2"}


def test_update_table_schema_rejects_unknown_or_no_properties(token_client):
    with pytest.raises(TypeError):
        token_client.update_table_schema(dataset_id=DS, table_schema_id=TABLE_ID, colour="red")
    with pytest.raises(ValueError):
        token_client.update_table_schema(dataset_id=DS, table_schema_id=TABLE_ID)


def test_order_table_schema(mock_router, token_client):
    route = mock_router.put(f"/dataschema/{DS}/tableSchema/order").mock(
        return_value=httpx.Response(200)
    )
    token_client.order_table_schema(dataset_id=DS, table_schema_id=TABLE_ID, position=0)
    assert body(route) == {"id": TABLE_ID, "position": 0}


def test_delete_table_schema(mock_router, token_client):
    route = mock_router.delete(f"/dataschema/{DS}/tableSchema/{TABLE_ID}").mock(
        return_value=httpx.Response(200)
    )
    token_client.delete_table_schema(dataset_id=DS, table_schema_id=TABLE_ID)
    assert route.called


def test_create_field_schema_sends_the_captured_body_and_returns_text_id(mock_router, token_client):
    route = mock_router.post(f"/dataschema/{DS}/fieldSchema").mock(
        return_value=httpx.Response(200, text="6af5ba92c6dc4400014d1f26",
                                    headers={"content-type": "text/plain"})
    )
    fid = token_client.create_field_schema(
        dataset_id=DS, record_id=RECORD_ID, name="ClaudeField", type="NUMBER_DECIMAL",
        description="field added by Claude",
    )
    assert fid == "6af5ba92c6dc4400014d1f26"
    assert body(route) == {
        "codelistItems": [], "description": "field added by Claude", "maxSize": None,
        "name": "ClaudeField", "pk": False, "readOnly": False, "referencedField": None,
        "required": False, "type": "NUMBER_DECIMAL", "idRecord": RECORD_ID,
    }


def test_create_codelist_and_link_fields(mock_router, token_client):
    route = mock_router.post(f"/dataschema/{DS}/fieldSchema").mock(
        return_value=httpx.Response(200, text="f2")
    )
    token_client.create_field_schema(dataset_id=DS, record_id=RECORD_ID, name="Status",
                                     type="CODELIST", codelist_items=["open", "closed"])
    assert body(route)["codelistItems"] == ["open", "closed"]
    token_client.create_field_schema(
        dataset_id=DS, record_id=RECORD_ID, name="Site", type="LINK", required=True,
        referenced_field={"idDatasetSchema": SCHEMA_ID, "idPk": FIELD_ID},
    )
    assert body(route)["referencedField"] == {"idDatasetSchema": SCHEMA_ID, "idPk": FIELD_ID}


def test_update_field_schema_sends_the_whole_payload(mock_router, token_client):
    route = mock_router.put(f"/dataschema/{DS}/fieldSchema").mock(return_value=httpx.Response(200))
    payload = {"codelistItems": [], "description": "helloworld", "maxSize": "100",
               "name": "helloWorld", "pk": False, "readOnly": False, "required": True,
               "type": "TEXT", "validExtensions": [], "id": FIELD_ID, "idRecord": RECORD_ID}
    token_client.update_field_schema(dataset_id=DS, payload=payload)
    assert body(route) == payload


def test_update_field_schema_refuses_a_partial_body(mock_router, token_client):
    route = mock_router.put(f"/dataschema/{DS}/fieldSchema")
    with pytest.raises(ValueError, match="whole field"):
        token_client.update_field_schema(
            dataset_id=DS, payload={"id": FIELD_ID, "description": "x"}
        )
    assert not route.called


def test_order_and_delete_field_schema(mock_router, token_client):
    order = mock_router.put(f"/dataschema/{DS}/fieldSchema/order").mock(
        return_value=httpx.Response(200)
    )
    delete = mock_router.delete(f"/dataschema/{DS}/fieldSchema/{FIELD_ID}").mock(
        return_value=httpx.Response(200)
    )
    token_client.order_field_schema(dataset_id=DS, field_schema_id=FIELD_ID, position=1)
    token_client.delete_field_schema(dataset_id=DS, field_schema_id=FIELD_ID)
    assert body(order) == {"id": FIELD_ID, "position": 1}
    assert delete.called


def test_export_table_definition_returns_csv_text(mock_router, token_client):
    csv = ("Field name,PK,Required,ReadOnly,Field description,Field type,Extra information\n"
           "Status,,false,false,site status,CODELIST,open;closed\n")
    route = mock_router.get(f"/dataschema/v1/{SCHEMA_ID}/exportFieldSchemas").mock(
        return_value=httpx.Response(200, content=("﻿" + csv).encode(),
                                    headers={"content-type": "application/octet-stream"})
    )
    out = token_client.export_table_definition(
        dataset_schema_id=SCHEMA_ID, dataset_id=DS, table_schema_id=TABLE_ID
    )
    assert out == csv
    assert params(route) == {"datasetId": str(DS), "tableSchemaId": TABLE_ID, "mimeType": "csv"}


def test_export_schema_definitions_uses_the_numeric_dataset_id(mock_router, token_client):
    mock_router.get(f"/dataschema/v1/dataset/{DS}/exportFieldSchemas").mock(
        return_value=httpx.Response(200, content=b"PK\x03\x04...")
    )
    assert token_client.export_schema_definitions(dataset_id=DS).startswith(b"PK")


def test_list_and_validate_schemas(mock_router, token_client):
    mock_router.get("/dataschema/getSchemas/dataflow/11468").mock(
        return_value=httpx.Response(200, json=[{
            "idDataSetSchema": SCHEMA_ID, "nameDatasetSchema": "X", "tableSchemas": [],
        }])
    )
    mock_router.get("/dataschema/validate/dataflow/11468").mock(
        return_value=httpx.Response(200, text="false")
    )
    assert [s.id for s in token_client.list_schemas(dataflow_id=11468)] == [SCHEMA_ID]
    assert token_client.validate_schemas(dataflow_id=11468) is False


def test_count_table_records(mock_router, token_client):
    route = mock_router.get(f"/dataset/TableValueDatasetDL/{DS}").mock(
        return_value=httpx.Response(200, json={"totalRecords": 7, "records": []})
    )
    assert token_client.count_table_records(dataset_id=DS, table_schema_id=TABLE_ID) == 7
    assert params(route)["idTableSchema"] == TABLE_ID
    assert params(route)["pageSize"] == "1"


@pytest.mark.parametrize("call", [
    lambda c: c.create_empty_dataset_schema(dataflow_id=1, name="x"),
    lambda c: c.create_table_schema(dataset_id=DS, name="x"),
    lambda c: c.delete_field_schema(dataset_id=DS, field_schema_id=FIELD_ID),
    lambda c: c.list_schemas(dataflow_id=1),
])
def test_api_key_client_is_refused_before_any_request(mock_router, client, call):
    with pytest.raises(SchemaDesignNotPermittedError, match="login token") as exc:
        call(client)
    assert isinstance(exc.value, AuthError)
    assert not mock_router.calls


def test_server_error_on_a_write_says_it_may_be_partly_applied(mock_router, token_client):
    route = mock_router.put(f"/dataschema/{DS}/fieldSchema").mock(return_value=httpx.Response(
        500, json={"message": "status 400 reading RulesControllerZuul#deleteRuleRequired"}
    ))
    with pytest.raises(SchemaWriteUncertainError, match="may be partly applied"):
        token_client.update_field_schema(dataset_id=DS, payload={
            "id": FIELD_ID, "idRecord": RECORD_ID, "name": "n", "type": "TEXT"})
    assert route.call_count == 1  # never retried


def test_load_balancer_outage_gets_a_clear_message(mock_router, token_client):
    mock_router.post(f"/dataschema/{DS}/fieldSchema").mock(return_value=httpx.Response(
        500, text="com.netflix.client.ClientException: Load balancer does not have "
                  "available server for client: dataflow"))
    with pytest.raises(SchemaWriteUncertainError, match="briefly unavailable"):
        token_client.create_field_schema(dataset_id=DS, record_id=RECORD_ID, name="x",
                                         type="TEXT")
