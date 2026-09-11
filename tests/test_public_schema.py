"""Reading a public dataflow's QC rules — the only programmatic route to rule SQL.

Every /rules/ endpoint refuses an API key, custodian keys included (measured on
dataflow 2003). downloadPublicSchemaInformation is unauthenticated and serves
the same spreadsheet the web UI exports, rule SQL and all.
"""

import io

import httpx
import pytest
import respx

from reportnet import (
    DataflowNotPublicError,
    PublicSchema,
    QcRule,
    get_public_schema,
)

BASE = "https://api.reportnet.europa.eu"
URL = f"{BASE}/dataflow/downloadPublicSchemaInformation/1748"


def _workbook(rows):
    """Build a spreadsheet shaped like Reportnet's export."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "QC rules"
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


HEADER = ["Table", "Field", "Shortcode", "Name", "Description", "Expression",
          "Type of QC", "Severity Level", "Message", "Automatic", "Enabled"]

def _sample():
    return _workbook([
        ["Descriptive data"],                       # a lone cell names the dataset
        [],
        HEADER,
        ["ReportPeriod", "repCode", "RP-4", "Date check", "desc",
         'Select * From dataset_98701."reportperiod" WHERE x', "FIELD", "WARNING",
         "msg", "No", "Yes"],
        ["UWWTPs", "", "U-31", "E-PRTR", "desc",
         'SELECT u.* FROM dataset_98701."uwwtps" u '
         'WHERE u.x not in (select y from dataset_98699."uwwtps")',
         "RECORD", "ERROR", "msg", "No", "Yes"],
        ["Agglomerations", "aggCode", "TB1", "Mandatory", "desc",
         "", "TABLE", "BLOCKER", "msg", "Yes", "Yes"],
        ["Spatial data"],                            # second dataset section
        [],
        HEADER,
        ["ProtectedArea", "", "FV05", "Format", "desc",
         "( thematicIdIdentifier MATCH ^FR.*$ )", "FIELD", "BLOCKER", "msg", "No", "Yes"],
    ])


@respx.mock
def test_rules_are_parsed_with_their_dataset_section():
    respx.get(URL).mock(return_value=httpx.Response(
        200, content=_sample(),
        headers={"content-disposition": 'attachment; filename=dataflow-1748-Schema.xlsx'},
    ))
    schema = get_public_schema(1748)
    assert isinstance(schema, PublicSchema)
    assert len(schema.rules) == 4
    assert schema.filename == "dataflow-1748-Schema.xlsx"
    # the lone-cell rows assign each rule to its dataset
    assert schema.by_dataset()["Descriptive data"][0].shortcode == "RP-4"
    assert schema.by_dataset()["Spatial data"][0].shortcode == "FV05"


@respx.mock
def test_sql_rules_are_distinguished_from_the_expression_language():
    """Automatic rules carry no expression; the rest are SQL or Reportnet's own
    ( field MATCH ^regex$ ) syntax. Only SQL is worth handing to a SQL tool."""
    respx.get(URL).mock(return_value=httpx.Response(200, content=_sample()))
    schema = get_public_schema(1748)
    assert [r.shortcode for r in schema.sql_rules()] == ["RP-4", "U-31"]
    codes = {r.shortcode: r for r in schema.rules}
    assert not codes["TB1"].is_sql, "no expression at all"
    assert not codes["FV05"].is_sql, "expression language, not SQL"


@respx.mock
def test_design_dataset_ids_are_extracted_in_order():
    """Rule SQL says dataset_<id>."table" and that id is a DESIGN dataset —
    resolve it with DataflowClient.get_design_datasets()."""
    respx.get(URL).mock(return_value=httpx.Response(200, content=_sample()))
    rules = {r.shortcode: r for r in get_public_schema(1748).rules}
    assert rules["RP-4"].dataset_ids == (98701,)
    assert rules["U-31"].dataset_ids == (98701, 98699), "cross-dataset rule, in order"
    assert rules["U-31"].tables_read == ("uwwtps",)
    assert rules["TB1"].dataset_ids == ()


@respx.mock
def test_a_private_dataflow_raises_something_actionable():
    """404 is what a private dataflow returns — including a private test copy of
    a public one (measured: 1748 public, its test twin 2003 not)."""
    respx.get(f"{BASE}/dataflow/downloadPublicSchemaInformation/2003").mock(
        return_value=httpx.Response(404, text="Not Found")
    )
    with pytest.raises(DataflowNotPublicError) as exc:
        get_public_schema(2003)
    assert exc.value.dataflow_id == 2003
    assert "web UI" in str(exc.value), "tell the caller what to do instead"


@respx.mock
def test_parsing_can_be_skipped_so_openpyxl_is_optional():
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"not-a-workbook"))
    schema = get_public_schema(1748, parse=False)
    assert schema.rules == ()
    assert schema.content == b"not-a-workbook"


@respx.mock
def test_the_original_spreadsheet_can_be_saved(tmp_path):
    respx.get(URL).mock(return_value=httpx.Response(
        200, content=_sample(),
        headers={"content-disposition": "attachment; filename=sheet.xlsx"},
    ))
    schema = get_public_schema(1748)
    written = schema.save(tmp_path)                 # directory -> uses the server's name
    assert written.name == "sheet.xlsx"
    assert written.read_bytes() == schema.content


def test_qc_rule_is_frozen():
    rule = QcRule(dataset="d", table="t", field="", shortcode="s", name="n",
                  description="", expression="", qc_type="FIELD", severity="ERROR",
                  message="m", automatic=False, enabled=True)
    with pytest.raises(Exception):
        rule.shortcode = "x"
