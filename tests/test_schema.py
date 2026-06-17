import httpx
import pytest

from reportnet import DatasetSchema, FieldType

SCHEMA_RESPONSE = {
    "idDataSetSchema": "schema-001",
    "nameDatasetSchema": "MyDataset",
    "description": "A test dataset",
    "tableSchemas": [
        {
            "idTableSchema": "table-001",
            "nameTableSchema": "Table1a",
            "description": "First table",
            "readOnly": False,
            "recordSchema": {
                "idRecordSchema": "record-001",
                "fieldSchema": [
                    {
                        "id": "field-001",
                        "name": "category",
                        "type": "LINK",
                        "description": "Category",
                        "required": True,
                    },
                    {
                        "id": "field-002",
                        "name": "cyear",
                        "type": "NUMBER_INTEGER",
                        "description": "Calendar year",
                        "required": True,
                    },
                    {
                        "id": "field-003",
                        "name": "cvalue",
                        "type": "NUMBER_DECIMAL",
                        "description": "Value",
                        "required": False,
                    },
                ],
            },
        }
    ],
}


def test_get_schema_returns_dataset_schema(mock_router, client):
    mock_router.get("/dataschema/v1/datasetId/1").mock(
        return_value=httpx.Response(200, json=SCHEMA_RESPONSE)
    )
    schema = client.get_schema(dataset_id=1)
    assert isinstance(schema, DatasetSchema)
    assert schema.id == "schema-001"
    assert schema.name == "MyDataset"
    assert len(schema.tables) == 1


def test_table_schema_fields(mock_router, client):
    mock_router.get("/dataschema/v1/datasetId/1").mock(
        return_value=httpx.Response(200, json=SCHEMA_RESPONSE)
    )
    schema = client.get_schema(dataset_id=1)
    table = schema.tables[0]
    assert table.name == "Table1a"
    assert len(table.fields) == 3
    assert table.fields[0].name == "category"
    assert table.fields[0].type == FieldType.LINK
    assert table.fields[0].required is True
    assert table.fields[2].required is False


def test_table_required_columns(mock_router, client):
    mock_router.get("/dataschema/v1/datasetId/1").mock(
        return_value=httpx.Response(200, json=SCHEMA_RESPONSE)
    )
    schema = client.get_schema(dataset_id=1)
    table = schema.table("Table1a")
    assert table.required_columns() == ["category", "cyear"]
    assert table.column_names() == ["category", "cyear", "cvalue"]


def test_schema_table_lookup_missing_raises(mock_router, client):
    mock_router.get("/dataschema/v1/datasetId/1").mock(
        return_value=httpx.Response(200, json=SCHEMA_RESPONSE)
    )
    schema = client.get_schema(dataset_id=1)
    with pytest.raises(KeyError, match="NoSuchTable"):
        schema.table("NoSuchTable")


def test_field_type_unknown_does_not_raise(mock_router, client):
    resp = {**SCHEMA_RESPONSE}
    resp["tableSchemas"][0]["recordSchema"]["fieldSchema"][0]["type"] = "FUTURE_TYPE"
    mock_router.get("/dataschema/v1/datasetId/1").mock(
        return_value=httpx.Response(200, json=resp)
    )
    schema = client.get_schema(dataset_id=1)
    assert schema.tables[0].fields[0].type.value == "FUTURE_TYPE"


@pytest.mark.integration
def test_get_schema_live():
    import reportnet

    try:
        client = reportnet.ReportnetClient.from_keyring(1619)
    except KeyError:
        pytest.skip("No API key in keyring for dataflow 1619")

    schema = client.get_schema(dataset_id=93953)
    assert schema.name == "Table1a"
    table = schema.table("Table1a")
    print(f"\n  {table.name}: {table.column_names()}")
    print(f"  required: {table.required_columns()}")
    assert "category" in table.required_columns()
    assert "cvalue" not in table.required_columns()
