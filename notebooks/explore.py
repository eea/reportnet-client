import marimo

__generated_with = "0.9.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # Reportnet Explorer

        Interactive exploration of the Reportnet 3 API.

        API keys are read from the system keychain.
        Store one with: `reportnet.save_key(dataflow_id=..., api_key="...")`
        """
    )
    return


@app.cell
def _():
    import reportnet

    DATAFLOW_ID = 1619   # change this
    return DATAFLOW_ID, reportnet


@app.cell
def _(DATAFLOW_ID, reportnet):
    client = reportnet.ReportnetClient.from_keyring(DATAFLOW_ID)
    df = client.for_dataflow(DATAFLOW_ID)
    info = df.get_dataflow()
    info
    return client, df, info


@app.cell
def _(df):
    reporters = df.get_reporters()
    reporters
    return (reporters,)


@app.cell
def _(mo):
    dataset_id_input = mo.ui.number(value=93953, label="Dataset ID")
    dataset_id_input
    return (dataset_id_input,)


@app.cell
def _(dataset_id_input, df):
    schema = df.get_schema(dataset_id=dataset_id_input.value)
    schema
    return (schema,)


@app.cell
def _(schema):
    # Show all tables and their columns with types
    import polars as pl

    rows = [
        {
            "table": t.name,
            "field": f.name,
            "type": str(f.type.value),
            "required": f.required,
        }
        for t in schema.tables
        for f in t.fields
    ]
    pl.DataFrame(rows)
    return (pl, rows)


@app.cell
def _(mo):
    table_name_input = mo.ui.text(value="Table1a", label="Table name")
    table_name_input
    return (table_name_input,)


@app.cell
def _(schema, table_name_input):
    # Empty DataFrame with correct column types — ready to populate and upload
    try:
        frame = schema.table(table_name_input.value).to_frame()
        frame
    except KeyError as e:
        frame = None
        print(e)
    return (frame,)


@app.cell
def _(dataset_id_input, df, mo):
    run_export = mo.ui.run_button(label="Export dataset (ETL)")
    mo.md(f"Export dataset **{dataset_id_input.value}** → DataFrames")
    return (run_export,)


@app.cell
def _(dataset_id_input, df, mo, run_export):
    mo.stop(not run_export.value)
    frames = df.etl_export(dataset_id=dataset_id_input.value).to_frames(
        poll_interval=5.0,
        timeout=600.0,
    )
    {name: f.shape for name, f in frames.items()}
    return (frames,)


if __name__ == "__main__":
    app.run()
