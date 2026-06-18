import marimo

__generated_with = "0.9.0"
app = marimo.App(width="medium", app_title="Reportnet — Explore a Dataflow")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # Explore a Dataflow

        This notebook walks through the Reportnet client hierarchy:

        ```
        Dataflow  →  Reporters (countries)  →  Datasets  →  Tables / Fields
        ```

        API keys are stored in your OS keychain.
        Save one with: `reportnet.save_key(dataflow_id=..., api_key="...")`
        """
    )
    return


# ── 1. Connect ────────────────────────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md("## 1. Connect")
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
        _df = _client.for_dataflow(DATAFLOW_ID)
        connect_ok = True
        client = _client
        df = _df
        mo.callout(mo.md(f"Connected to dataflow **{DATAFLOW_ID}**"), kind="success")
    except KeyError:
        connect_ok = False
        client = None
        df = None
        mo.callout(
            mo.md(
                f"No API key found for dataflow {DATAFLOW_ID}.  \n"
                f"Run: `reportnet.save_key({DATAFLOW_ID}, 'your-key')`"
            ),
            kind="danger",
        )
    return client, connect_ok, df


# ── 2. Dataflow metadata ──────────────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md("## 2. Dataflow metadata")
    return


@app.cell
def _(connect_ok, df, mo):
    mo.stop(not connect_ok)
    info = df.get_dataflow()
    is_big = df.is_big_dataflow()
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
    return info, is_big


# ── 3. Reporters ──────────────────────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md("## 3. Reporters (countries)")
    return


@app.cell
def _(connect_ok, df, mo):
    import polars as pl

    mo.stop(not connect_ok)
    reporters = df.get_reporters()

    reporter_table = pl.DataFrame({
        "provider_id": [r.provider_id for r in reporters],
        "dataset_id":  [r.dataset_id  for r in reporters],
    })
    mo.ui.table(reporter_table.to_pandas() if not hasattr(reporter_table, "to_arrow") else reporter_table)
    return pl, reporter_table, reporters


@app.cell
def _(mo, reporters):
    provider_selector = mo.ui.dropdown(
        options={str(r.provider_id): r.provider_id for r in reporters},
        label="Select reporter",
    )
    provider_selector
    return (provider_selector,)


@app.cell
def _(df, mo, provider_selector, reporters):
    mo.stop(provider_selector.value is None)
    selected_reporter = next(r for r in reporters if r.provider_id == provider_selector.value)
    scoped = df.for_provider(selected_reporter.provider_id)
    mo.md(
        f"**Provider ID:** {selected_reporter.provider_id}  \n"
        f"**Dataset ID:** {selected_reporter.dataset_id}"
    )
    return scoped, selected_reporter


# ── 4. Dataset schema ─────────────────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md("## 4. Dataset schema")
    return


@app.cell
def _(mo, scoped, selected_reporter):
    schema = scoped.get_schema(dataset_id=selected_reporter.dataset_id)
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
        "field":    [f.name        for f in selected_table.fields],
        "type":     [f.type.value  for f in selected_table.fields],
        "required": [f.required    for f in selected_table.fields],
    })
    mo.vstack([
        mo.md(f"### `{selected_table.name}` fields"),
        mo.ui.table(field_rows),
    ])
    return field_rows, selected_table


# ── 5. Empty DataFrame with correct types ─────────────────────────────────────

@app.cell
def _(mo):
    mo.md(
        """
        ## 5. Empty DataFrame template

        `to_frame()` returns an empty DataFrame with the correct column names
        and types — use it as a template for building import data.
        """
    )
    return


@app.cell
def _(mo, selected_table):
    empty = selected_table.to_frame()
    mo.vstack([
        mo.md(f"Shape: `{empty.shape}`  —  Schema:"),
        mo.ui.table(empty),
    ])
    return (empty,)


# ── 6. Release history ────────────────────────────────────────────────────────

@app.cell
def _(mo):
    mo.md("## 6. Historic releases")
    return


@app.cell
def _(mo, pl, scoped, selected_reporter):
    releases = scoped.list_historic_releases(dataset_id=selected_reporter.dataset_id)
    if releases:
        mo.ui.table(pl.DataFrame(releases))
    else:
        mo.callout(mo.md("No releases found for this dataset."), kind="info")
    return (releases,)


if __name__ == "__main__":
    app.run()
