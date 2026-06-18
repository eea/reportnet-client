import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium", app_title="Reportnet — Explore a Dataflow")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(r"""
    # Explore a Dataflow

    This notebook walks through the Reportnet client hierarchy:

    ```
    Dataflow  →  Reporters (countries)  →  Datasets  →  Tables / Fields
    ```

    API keys are stored in your OS keychain.
    Save one with: `reportnet.save_key(dataflow_id=..., api_key="...")`
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 1. Connect
    """)
    return


@app.cell
def _():
    import reportnet

    DATAFLOW_ID = 1619
    return DATAFLOW_ID, reportnet


@app.cell
def _(DATAFLOW_ID, mo, reportnet):
    try:
        _client = reportnet.ReportnetClient.from_keyring(DATAFLOW_ID)
        _flow = _client.for_dataflow(DATAFLOW_ID)
        if not _flow.ping():
            raise reportnet.AuthError("API key is invalid or has been revoked")
        connect_ok = True
        flow = _flow
        mo.callout(mo.md(f"Connected to dataflow **{DATAFLOW_ID}**"), kind="success")
    except KeyError:
        connect_ok = False
        flow = None
        mo.callout(
            mo.md(
                f"No API key found for dataflow {DATAFLOW_ID}.  \n"
                f"Run: `reportnet.save_key({DATAFLOW_ID}, 'your-key')`"
            ),
            kind="danger",
        )
    except reportnet.AuthError:
        connect_ok = False
        flow = None
        mo.callout(mo.md("API key is invalid or has been revoked"), kind="danger")
    return connect_ok, flow


@app.cell
def _(mo):
    mo.md("""
    ## 2. Dataflow metadata
    """)
    return


@app.cell
def _(connect_ok, flow, mo):
    mo.stop(not connect_ok)
    info = flow.get_dataflow()
    is_big = flow.is_big_dataflow()
    mo.md(
        f"""
        | | |
        |---|---|
        | **Name** | {info.name} |
        | **Type** | {info.type} |
        | **Status** | {info.status} |
        | **Backend** | {"BigData (DLT2)" if is_big else "Citus"} |
        """
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3. Reporters (countries)
    """)
    return


@app.cell
def _(connect_ok, flow, mo):
    import polars as pl

    mo.stop(not connect_ok)
    reporters = flow.get_reporters()
    reporting_datasets = flow.get_reporting_datasets()
    reference_datasets = flow.get_reference_datasets()

    # Build lookup: provider_id → list of ReportingDataset
    ds_by_provider: dict = {}
    for _ds in reporting_datasets:
        ds_by_provider.setdefault(_ds.provider_id, []).append(_ds)

    reporter_table = pl.DataFrame({
        "country":      [r.country_code or "?"  for r in reporters],
        "country_name": [r.country_name or ""   for r in reporters],
        "provider_id":  [r.provider_id           for r in reporters],
        "datasets":     [len(ds_by_provider.get(r.provider_id, [])) for r in reporters],
    })
    mo.ui.table(reporter_table)
    return ds_by_provider, pl, reference_datasets, reporters


@app.cell
def _(mo, reporters):
    provider_selector = mo.ui.dropdown(
        options={
            f"{r.country_code or '?'} — {r.country_name or r.provider_id}": r.provider_id
            for r in reporters
        },
        label="Select reporter",
    )
    provider_selector
    return (provider_selector,)


@app.cell
def _(ds_by_provider, flow, mo, provider_selector, reporters):
    mo.stop(provider_selector.value is None)
    selected_reporter = next(
        r for r in reporters if r.provider_id == provider_selector.value
    )
    scoped = flow.for_provider(selected_reporter.provider_id)
    provider_datasets = ds_by_provider.get(selected_reporter.provider_id, [])
    mo.md(
        f"**{selected_reporter.country_name or '?'}** "
        f"(provider {selected_reporter.provider_id}) — "
        f"{len(provider_datasets)} dataset(s)"
    )
    return provider_datasets, scoped


@app.cell
def _(mo, provider_datasets):
    dataset_selector = mo.ui.dropdown(
        options={ds.table_name: ds for ds in provider_datasets},
        label="Select dataset (table)",
    )
    dataset_selector
    return (dataset_selector,)


@app.cell
def _(dataset_selector, mo):
    mo.stop(dataset_selector.value is None)
    selected_dataset = dataset_selector.value
    mo.md(
        f"**Dataset ID:** {selected_dataset.id}  \n"
        f"**Table:** {selected_dataset.table_name}  \n"
        f"**Status:** {selected_dataset.status}"
    )
    return (selected_dataset,)


@app.cell
def _(mo):
    mo.md("""
    ## 4. Dataset schema
    """)
    return


@app.cell
def _(mo, scoped, selected_dataset):
    schema = scoped.get_schema(dataset_id=selected_dataset.id)
    mo.md(
        f"**{schema.name}** — {len(schema.tables)} table(s):  \n"
        + "  \n".join(f"- `{t.name}` ({len(t.fields)} fields)" for t in schema.tables)
    )
    return (schema,)


@app.cell
def _(mo, schema):
    table_selector = mo.ui.dropdown(
        options=[t.name for t in schema.tables],
        label="Select table",
    )
    table_selector
    return (table_selector,)


@app.cell
def _(mo, pl, schema, table_selector):
    mo.stop(table_selector.value is None)
    selected_table = schema.table(table_selector.value)

    field_rows = pl.DataFrame({
        "field":      [f.name                        for f in selected_table.fields],
        "type":       [f.type.value                  for f in selected_table.fields],
        "required":   [f.required                    for f in selected_table.fields],
        "ref_schema": [f.referenced_schema_id or ""  for f in selected_table.fields],
    })
    mo.vstack([
        mo.md(f"### `{selected_table.name}` fields"),
        mo.ui.table(field_rows),
    ])
    return (selected_table,)


@app.cell
def _(mo):
    mo.md("""
    ## 5. Empty DataFrame template

    `to_frame()` returns an empty DataFrame with the correct column names
    and types — use it as a template for building import data.

    Pass a `ref_dataset_id` below to resolve LINK field codelists.
    Leave blank to skip (LINK columns stay as plain strings).
    """)
    return


@app.cell
def _(mo, reference_datasets):
    _ref_options = {"(none — skip codelist resolution)": None}
    _ref_options.update({ds.name: ds.id for ds in reference_datasets})
    ref_dataset_selector = mo.ui.dropdown(
        options=_ref_options,
        label="Reference dataset",
    )
    ref_dataset_selector
    return (ref_dataset_selector,)


@app.cell
def _(mo, ref_dataset_selector, scoped, selected_dataset, selected_table):
    _ref_id = ref_dataset_selector.value
    if _ref_id is not None:
        with mo.status.spinner("Resolving codelists…"):
            _codelists = scoped.get_codelists(
                dataset_id=selected_dataset.id,
                ref_dataset_id=_ref_id,
            )
    else:
        _codelists = None

    empty = selected_table.to_frame(codelists=_codelists)
    _schema_str = {col: str(dt) for col, dt in zip(empty.columns, empty.dtypes)}
    mo.vstack([
        mo.md(f"Shape: `{empty.shape}`  —  Schema: `{_schema_str}`"),
        mo.ui.table(empty),
    ])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 6. Historic releases
    """)
    return


@app.cell
def _(mo, pl, scoped, selected_dataset):
    releases = scoped.list_historic_releases(dataset_id=selected_dataset.id)
    if releases:
        mo.ui.table(pl.DataFrame(releases))
    else:
        mo.callout(mo.md("No releases found for this dataset."), kind="info")
    return


if __name__ == "__main__":
    app.run()
