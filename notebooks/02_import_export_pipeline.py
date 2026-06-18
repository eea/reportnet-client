import marimo

__generated_with = "0.9.0"
app = marimo.App(width="medium", app_title="Reportnet — Import / Export Pipeline")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # Import / Export Pipeline

        A complete data cycle:

        1. **Export** existing data to DataFrames
        2. **Inspect** what's there
        3. **Build** new rows using the schema as a template
        4. **Import** the new data
        5. **Validate** and read back results
        """
    )
    return


# ── Setup ─────────────────────────────────────────────────────────────────────

@app.cell
def _():
    import reportnet

    DATAFLOW_ID  = 1619
    DATASET_ID   = 93953
    PROVIDER_ID  = None   # None = custodian; set to reporter's provider_id if needed
    TABLE_SCHEMA_ID = "68dd41f045f9450001260da7"   # from Reportnet URL tab fragment
    return DATAFLOW_ID, DATASET_ID, PROVIDER_ID, TABLE_SCHEMA_ID, reportnet


@app.cell
def _(DATAFLOW_ID, PROVIDER_ID, mo, reportnet):
    try:
        _client = reportnet.ReportnetClient.from_keyring(DATAFLOW_ID)
        if PROVIDER_ID is not None:
            df_client = _client.for_dataflow(DATAFLOW_ID).for_provider(PROVIDER_ID)
        else:
            df_client = _client.for_dataflow(DATAFLOW_ID)
        connect_ok = True
        mo.callout(mo.md("Connected"), kind="success")
    except KeyError:
        df_client = None
        connect_ok = False
        mo.callout(mo.md(f"No API key for dataflow {DATAFLOW_ID}"), kind="danger")
    return connect_ok, df_client


# ── 1. Export ─────────────────────────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md(
        """
        ## 1. Export existing data

        `etl_export().to_frames()` returns all tables as DataFrames in one call.
        """
    )
    return


@app.cell
def _(mo):
    export_btn = mo.ui.run_button(label="Export dataset")
    export_btn
    return (export_btn,)


@app.cell
def _(DATASET_ID, connect_ok, df_client, export_btn, mo):
    mo.stop(not connect_ok or not export_btn.value)

    with mo.status.spinner("Exporting…"):
        frames = df_client.etl_export(
            dataset_id=DATASET_ID,
        ).to_frames(poll_interval=5.0, timeout=600.0)

    mo.callout(
        mo.md("  \n".join(f"**{name}**: {f.shape[0]} rows × {f.shape[1]} cols"
                          for name, f in frames.items())),
        kind="success",
    )
    return (frames,)


# ── 2. Inspect ────────────────────────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md("## 2. Inspect the data")
    return


@app.cell
def _(frames, mo):
    table_pick = mo.ui.dropdown(options=list(frames), label="Table")
    table_pick
    return (table_pick,)


@app.cell
def _(frames, mo, table_pick):
    mo.stop(table_pick.value is None)
    current_frame = frames[table_pick.value]
    mo.vstack([
        mo.md(f"**{table_pick.value}** — {current_frame.shape[0]} rows × {current_frame.shape[1]} cols"),
        mo.ui.table(current_frame.head(50)),
    ])
    return (current_frame,)


# ── 3. Build new rows from schema ─────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md(
        """
        ## 3. Build new rows

        `get_schema()` + `to_frame()` gives an empty DataFrame with the correct
        column types. Populate it, then concatenate with existing data or import
        directly.
        """
    )
    return


@app.cell
def _(DATASET_ID, connect_ok, df_client, mo):
    import polars as pl

    mo.stop(not connect_ok)
    schema = df_client.get_schema(dataset_id=DATASET_ID)

    # Show the schema as a table
    field_info = pl.DataFrame({
        "table":    [t.name       for t in schema.tables for f in t.fields],
        "field":    [f.name       for t in schema.tables for f in t.fields],
        "type":     [f.type.value for t in schema.tables for f in t.fields],
        "required": [f.required   for t in schema.tables for f in t.fields],
    })
    mo.vstack([
        mo.md(f"Schema: **{schema.name}**"),
        mo.ui.table(field_info),
    ])
    return field_info, pl, schema


@app.cell
def _(mo, pl, schema):
    # Get an empty template DataFrame for Table1a
    try:
        template = schema.table("Table1a").to_frame()
    except KeyError:
        template = schema.tables[0].to_frame()

    mo.vstack([
        mo.md(f"Empty template — dtypes: `{dict(zip(template.columns, [str(d) for d in template.dtypes]))}`"),
        mo.ui.table(template),
    ])

    # Build new rows — edit these values to match your data
    new_rows = pl.DataFrame({
        "category":                ["Total including LULUCF",  "Total excluding LULUCF"],
        "scenario":                ["WEM",                     "WEM"],
        "ry":                      ["0",                       "0"],
        "cyear":                   [2024,                      2024],
        "gas":                     ["Total GHG emissions (ktCO2e)", "CO2 (ktCO2e)"],
        "cvalue":                  [1111.0,                    2222.0],
        "notation":                ["NA",                      "NA"],
        "inventorySubmissionYear": [2024,                      2024],
    }).cast({col: template.schema[col] for col in template.columns if col in template.schema})

    mo.md(f"New rows to import: **{new_rows.shape[0]}**")
    return new_rows, template


# ── 4. Import ─────────────────────────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md("## 4. Import new rows")
    return


@app.cell
def _(mo, new_rows):
    mo.vstack([
        mo.md("Preview of rows to upload:"),
        mo.ui.table(new_rows),
    ])
    return


@app.cell
def _(mo):
    import_btn = mo.ui.run_button(label="Import rows", kind="danger")
    mo.callout(
        mo.hstack([import_btn, mo.md(" Appends rows to the dataset — cannot be undone easily.")]),
        kind="warn",
    )
    return (import_btn,)


@app.cell
def _(
    DATASET_ID,
    TABLE_SCHEMA_ID,
    connect_ok,
    df_client,
    import_btn,
    mo,
    new_rows,
):
    mo.stop(not connect_ok or not import_btn.value)

    with mo.status.spinner("Importing…"):
        import_handle = df_client.import_file(
            dataset_id=DATASET_ID,
            file=new_rows,
            table_schema_id=TABLE_SCHEMA_ID,
            replace=False,
        )
        import_handle.wait(poll_interval=5.0, timeout=300.0)

    mo.callout(mo.md("Import finished"), kind="success")
    return (import_handle,)


# ── 5. Validate ───────────────────────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md("## 5. Validate")
    return


@app.cell
def _(mo):
    validate_btn = mo.ui.run_button(label="Run validation")
    validate_btn
    return (validate_btn,)


@app.cell
def _(DATASET_ID, connect_ok, df_client, mo, reportnet, validate_btn):
    mo.stop(not connect_ok or not validate_btn.value)

    try:
        with mo.status.spinner("Validating…"):
            val_handle = df_client.add_validation_job(dataset_id=DATASET_ID)
            val_handle.wait(poll_interval=10.0, timeout=600.0)
        mo.callout(mo.md("Validation finished"), kind="success")
    except reportnet.DatasetLockedError:
        mo.callout(mo.md("Dataset locked — another job is running. Try again shortly."), kind="warn")
    return (val_handle,)


@app.cell
def _(DATASET_ID, connect_ok, df_client, mo):
    mo.stop(not connect_ok)
    validation_results = df_client.list_group_validations_dl(dataset_id=DATASET_ID)
    mo.md(f"Validation result keys: `{list(validation_results)[:8]}`")
    return (validation_results,)


# ── 6. Verify via re-export ───────────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md("## 6. Verify via re-export")
    return


@app.cell
def _(mo):
    verify_btn = mo.ui.run_button(label="Re-export to verify")
    verify_btn
    return (verify_btn,)


@app.cell
def _(DATASET_ID, connect_ok, df_client, mo, verify_btn):
    mo.stop(not connect_ok or not verify_btn.value)

    with mo.status.spinner("Exporting…"):
        updated_frames = df_client.etl_export(dataset_id=DATASET_ID).to_frames(
            poll_interval=5.0, timeout=600.0
        )

    mo.vstack([
        mo.md("Updated row counts:"),
        mo.md("  \n".join(
            f"- **{name}**: {f.shape[0]} rows" for name, f in updated_frames.items()
        )),
    ])
    return (updated_frames,)


if __name__ == "__main__":
    app.run()
