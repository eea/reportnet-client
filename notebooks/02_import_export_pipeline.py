import marimo

__generated_with = "0.23.6"
app = marimo.App(
    width="medium",
    app_title="Reportnet — Import / Export Pipeline",
)


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(r"""
    # Import / Export Pipeline

    A complete data cycle for a country reporter:

    1. **Connect** — load your API key from the keychain
    2. **Discover** — find your dataset ID and schema
    3. **Build data** — from an Excel file, CSV, or Python DataFrame
    4. **Validate** — check columns and codelist values before uploading
    5. **Import** — upload to Reportnet
    6. **Verify** — re-export to confirm the upload

    ---

    **Setup** — enter your Dataflow ID below, then expand *Save API key* to store
    your key in the system keychain (once only).
    """)
    return


@app.cell
def _(mo):
    mo.md("## 1. Connect")
    return


@app.cell
def _(mo):
    dataflow_id_cfg = mo.ui.number(value=1619, label="Dataflow ID", step=1)
    country_code_cfg = mo.ui.text(value="IE", label="Country code (ISO 3166-1 α-2)")
    sandbox_cfg = mo.ui.checkbox(label="Sandbox (sandbox.reportnet.europa.eu)")
    mo.hstack([dataflow_id_cfg, country_code_cfg, sandbox_cfg])
    return country_code_cfg, dataflow_id_cfg, sandbox_cfg


@app.cell
def _(dataflow_id_cfg, mo, sandbox_cfg):
    _did = int(dataflow_id_cfg.value)
    _env = "sandbox" if sandbox_cfg.value else "production"
    key_input_02 = mo.ui.text(
        placeholder="paste your API key here",
        kind="password",
        label="API key",
        full_width=True,
    )
    save_btn_02 = mo.ui.run_button(label="Save to keychain")
    mo.accordion({
        f"🔑 Save API key for dataflow {_did} ({_env})": mo.vstack([
            mo.md("Saves the key to your system keychain — only needed once per dataflow."),
            key_input_02,
            save_btn_02,
        ])
    })
    return key_input_02, save_btn_02


@app.cell
def _(dataflow_id_cfg, key_input_02, mo, sandbox_cfg, save_btn_02):
    import reportnet as _rn02
    mo.stop(not save_btn_02.value or not key_input_02.value)
    _rn02.save_key(int(dataflow_id_cfg.value), key_input_02.value, sandbox=sandbox_cfg.value)
    mo.callout(mo.md("API key saved — re-run the cell above to connect."), kind="success")


@app.cell
def _(country_code_cfg, dataflow_id_cfg, mo, sandbox_cfg):
    import reportnet

    DATAFLOW_ID = int(dataflow_id_cfg.value)
    COUNTRY_CODE = country_code_cfg.value.strip().upper()

    try:
        _client = reportnet.ReportnetClient.from_keyring(DATAFLOW_ID, sandbox=sandbox_cfg.value)
        _flow_base = _client.for_dataflow(DATAFLOW_ID)
        # find_reporter looks up the provider_id from the country code automatically
        flow = _flow_base.find_reporter(COUNTRY_CODE)
        connect_ok = True
        _env_label = "sandbox" if sandbox_cfg.value else "production"
        mo.callout(
            mo.md(f"Connected as **{COUNTRY_CODE}** on dataflow **{DATAFLOW_ID}** ({_env_label})"),
            kind="success",
        )
    except KeyError:
        flow = None
        connect_ok = False
        mo.callout(
            mo.md(
                f"No API key found for dataflow {DATAFLOW_ID}.  \n"
                f"Expand *Save API key* above to store your key."
            ),
            kind="danger",
        )
    except ValueError as _e:
        flow = None
        connect_ok = False
        mo.callout(mo.md(f"Country lookup failed: {_e}"), kind="danger")
    except reportnet.AuthError:
        flow = None
        connect_ok = False
        mo.callout(mo.md("API key is invalid or has been revoked."), kind="danger")
    return COUNTRY_CODE, DATAFLOW_ID, connect_ok, flow, reportnet


@app.cell
def _(mo):
    mo.md("## 2. Discover datasets and schema")
    return


@app.cell
def _(connect_ok, flow, mo):
    import polars as pl

    mo.stop(not connect_ok)
    datasets = flow.get_reporting_datasets()   # auto-filtered to your country
    mo.callout(
        mo.md(
            f"Found **{len(datasets)}** dataset(s).  \n"
            + "  \n".join(
                f"- `{ds.table_name}` → dataset_id **{ds.id}** (status: {ds.status})"
                for ds in datasets
            )
        ),
        kind="info",
    )
    return datasets, pl


@app.cell
def _(datasets, mo):
    dataset_selector = mo.ui.dropdown(
        options={ds.table_name: ds for ds in datasets},
        label="Select dataset to work with",
    )
    dataset_selector
    return (dataset_selector,)


@app.cell
def _(dataset_selector, flow, mo, pl):
    mo.stop(dataset_selector.value is None)
    target_dataset = dataset_selector.value

    schema = flow.get_schema(dataset_id=target_dataset.id)

    # Build fully-typed templates in one call — resolves LINK/CODELIST → Enum automatically
    with mo.status.spinner("Building typed templates (fetching codelists)…"):
        templates = flow.get_template(dataset_id=target_dataset.id)

    field_info = pl.DataFrame({
        "table":    [t.name       for t in schema.tables for f in t.fields],
        "field":    [f.name       for t in schema.tables for f in t.fields],
        "type":     [f.type.value for t in schema.tables for f in t.fields],
        "required": [f.required   for t in schema.tables for f in t.fields],
    })
    enum_cols = [col for t in templates.values() for col, dt in zip(t.columns, t.dtypes)
                 if isinstance(dt, pl.Enum)]
    mo.vstack([
        mo.md(
            f"Schema: **{schema.name}**  — "
            + (f"Enum columns: `{enum_cols}`" if enum_cols else "no Enum columns")
        ),
        mo.ui.table(field_info),
    ])
    return schema, target_dataset, templates


@app.cell
def _(mo):
    mo.md("""
    ## 3. Build data to upload

    Choose one of the three approaches below.

    ---

    ### Option A — from an Excel file

    ```python
    # Each sheet should match a table name in the schema.
    # Columns must match the field names shown above.
    import polars as pl

    df = pl.read_excel("my_data.xlsx", sheet_name="Table1a")
    ```

    ### Option B — from a CSV file

    ```python
    df = pl.read_csv("my_data.csv", separator="|")
    # or with pandas:
    # import pandas as pd
    # df = pd.read_csv("my_data.csv", sep="|")
    ```

    ### Option C — build rows in Python

    Use the empty template below as a starting point.
    LINK / CODELIST columns show their allowed values as Enum categories.
    """)
    return


@app.cell
def _(mo, templates):
    table_selector = mo.ui.dropdown(
        options=list(templates),
        label="Select table",
    )
    table_selector
    return (table_selector,)


@app.cell
def _(mo, pl, schema, table_selector, templates):
    mo.stop(table_selector.value is None)
    selected_table_schema = schema.table(table_selector.value)
    template = templates[table_selector.value]

    # Show allowed values for Enum (LINK / CODELIST) columns
    _enum_rows = [
        {"column": col, "valid_values": ", ".join(str(c) for c in dtype.categories)}
        for col, dtype in template.schema.items()
        if isinstance(dtype, pl.Enum)
    ]
    mo.vstack([
        mo.md(f"**Empty template** — {len(template.columns)} columns"),
        mo.ui.table(pl.DataFrame(_enum_rows)) if _enum_rows else mo.md("*(no Enum columns)*"),
        mo.ui.table(template),
    ])
    return selected_table_schema, template


@app.cell
def _(mo):
    mo.md("""
    ## 4. Validate before uploading

    `validate_frame()` checks required columns and Enum values.
    Enum columns already enforce valid values at assignment time — this
    catches any remaining issues (e.g. missing required columns).
    """)
    return


@app.cell
def _(mo, selected_table_schema, template):
    # Replace `template` with your actual DataFrame when ready.
    # Here we validate the empty template to show the mechanism.
    _errors = selected_table_schema.validate_frame(template)
    if _errors:
        mo.callout(
            mo.vstack([mo.md("**Validation errors:**")] + [mo.md(f"- {e}") for e in _errors]),
            kind="warn",
        )
    else:
        mo.callout(mo.md("Frame is valid — ready to upload."), kind="success")
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5. Import

    Replace `template` with your populated DataFrame (or a file path / bytes).
    The `replace=True` flag deletes all existing rows first; omit it to append.
    """)
    return


@app.cell
def _(mo):
    import_btn = mo.ui.run_button(label="Import data", kind="danger")
    mo.callout(
        mo.hstack([import_btn, mo.md(" Uploads data to Reportnet — cannot be undone easily.")]),
        kind="warn",
    )
    return (import_btn,)


@app.cell
def _(connect_ok, flow, import_btn, mo, target_dataset, template):
    mo.stop(not connect_ok or not import_btn.value)

    with mo.status.spinner("Importing…"):
        _handle = flow.import_file(
            dataset_id=target_dataset.id,
            file=template,        # swap in your real DataFrame / file path
            replace=False,        # set True to replace all existing rows
        )
        _handle.wait(poll_interval=5.0, timeout=300.0)

    mo.callout(mo.md("Import finished."), kind="success")
    return


@app.cell
def _(mo):
    mo.md("""
    ## 6. Validate the uploaded data

    `validate()` triggers a Reportnet validation job, waits for it, and returns
    a structured `ValidationResult` with `.has_blockers`, `.has_errors`, `.summary()`,
    and `.to_frame()` — no manual polling needed.
    """)
    return


@app.cell
def _(mo):
    validate_btn = mo.ui.run_button(label="Run validation")
    validate_btn
    return (validate_btn,)


@app.cell
def _(connect_ok, flow, mo, target_dataset, validate_btn):
    mo.stop(not connect_ok or not validate_btn.value)

    with mo.status.spinner("Running validation…"):
        _result = flow.validate(
            dataset_id=target_dataset.id,
            poll_interval=10.0,
            timeout=600.0,
        )

    if _result.has_blockers:
        mo.callout(
            mo.vstack([
                mo.md(f"**Blockers found** — cannot submit.  {_result.summary()}"),
                mo.ui.table(_result.to_frame()),
            ]),
            kind="danger",
        )
    elif _result.has_errors:
        mo.callout(
            mo.vstack([
                mo.md(f"**Errors found**.  {_result.summary()}"),
                mo.ui.table(_result.to_frame()),
            ]),
            kind="warn",
        )
    else:
        mo.callout(mo.md(f"Validation passed. {_result.summary()}"), kind="success")
    return


@app.cell
def _(mo):
    mo.md("## 7. Verify — export and inspect")
    return


@app.cell
def _(mo):
    verify_btn = mo.ui.run_button(label="Export to verify")
    verify_btn
    return (verify_btn,)


@app.cell
def _(connect_ok, flow, mo, target_dataset, verify_btn):
    mo.stop(not connect_ok or not verify_btn.value)

    with mo.status.spinner("Exporting…"):
        _frames = flow.etl_export(dataset_id=target_dataset.id).to_frames(
            poll_interval=5.0, timeout=600.0
        )

    mo.vstack([
        mo.md("**Row counts after import:**"),
        mo.md("  \n".join(
            f"- **{name}**: {f.shape[0]} rows × {f.shape[1]} cols"
            for name, f in _frames.items()
        )),
    ])
    return


if __name__ == "__main__":
    app.run()
