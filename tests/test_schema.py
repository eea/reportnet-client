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
                        "referencedField": {
                            "idDatasetSchema": "ref-schema-001",
                            "idPk": "ref-pk-001",
                            "labelId": None,
                        },
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

REF_SCHEMA_RESPONSE = {
    "idDataSetSchema": "ref-schema-001",
    "nameDatasetSchema": "Codelists",
    "description": "Reference data",
    "tableSchemas": [
        {
            "idTableSchema": "ref-table-001",
            "nameTableSchema": "Categories",
            "description": "",
            "recordSchema": {
                "idRecordSchema": "ref-record-001",
                "fieldSchema": [
                    {
                        "id": "ref-pk-001",
                        "name": "code",
                        "type": "TEXT",
                        "description": "Code",
                        "required": True,
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


def test_field_schema_parses_referenced_field(mock_router, client):
    mock_router.get("/dataschema/v1/datasetId/1").mock(
        return_value=httpx.Response(200, json=SCHEMA_RESPONSE)
    )
    schema = client.get_schema(dataset_id=1)
    category = schema.tables[0].fields[0]
    assert category.referenced_schema_id == "ref-schema-001"
    assert category.referenced_pk_id == "ref-pk-001"

    cyear = schema.tables[0].fields[1]
    assert cyear.referenced_schema_id is None
    assert cyear.referenced_pk_id is None


def test_to_frame_returns_empty_dataframe_with_correct_types(mock_router, client):
    pytest.importorskip("polars")
    import polars as pl

    mock_router.get("/dataschema/v1/datasetId/1").mock(
        return_value=httpx.Response(200, json=SCHEMA_RESPONSE)
    )
    schema = client.get_schema(dataset_id=1)
    table = schema.table("Table1a")
    frame = table.to_frame()

    assert isinstance(frame, pl.DataFrame)
    assert frame.shape == (0, 3)
    assert frame.columns == ["category", "cyear", "cvalue"]
    assert frame.dtypes[0] == pl.String    # LINK without codelists → String
    assert frame.dtypes[1] == pl.Int64     # NUMBER_INTEGER
    assert frame.dtypes[2] == pl.Float64   # NUMBER_DECIMAL


def test_to_frame_with_codelists_uses_enum(mock_router, client):
    pytest.importorskip("polars")
    import polars as pl

    mock_router.get("/dataschema/v1/datasetId/1").mock(
        return_value=httpx.Response(200, json=SCHEMA_RESPONSE)
    )
    schema = client.get_schema(dataset_id=1)
    table = schema.table("Table1a")

    codelists = {"category": ["Total excluding LULUCF", "Total including LULUCF"]}
    frame = table.to_frame(codelists=codelists)

    assert isinstance(frame, pl.DataFrame)
    assert isinstance(frame.dtypes[0], pl.Enum)
    assert frame.dtypes[0].categories.to_list() == [
        "Total excluding LULUCF",
        "Total including LULUCF",
    ]
    assert frame.dtypes[1] == pl.Int64     # unaffected


def test_dataset_schema_to_frames(mock_router, client):
    pytest.importorskip("polars")

    mock_router.get("/dataschema/v1/datasetId/1").mock(
        return_value=httpx.Response(200, json=SCHEMA_RESPONSE)
    )
    schema = client.get_schema(dataset_id=1)
    frames = schema.to_frames()

    assert list(frames) == ["Table1a"]
    assert frames["Table1a"].shape == (0, 3)


def test_build_codelists():
    pytest.importorskip("polars")
    import polars as pl

    from reportnet._util import build_codelists
    from reportnet.models import DatasetSchema

    reporting_schema = DatasetSchema.from_dict(SCHEMA_RESPONSE)
    ref_schema = DatasetSchema.from_dict(REF_SCHEMA_RESPONSE)
    ref_frames = {"Categories": pl.DataFrame({"code": ["B", "A", "C"]})}

    codelists = build_codelists(reporting_schema, ref_schema, ref_frames)

    # Only the LINK field (category) should be included; values are sorted
    assert set(codelists) == {"category"}
    assert codelists["category"] == ["A", "B", "C"]


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
