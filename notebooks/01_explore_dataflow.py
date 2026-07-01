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

    Use this notebook to orient yourself before reporting:

    - Find your country's datasets and their IDs
    - Inspect table schemas (column names, types, required fields)
    - Download an empty DataFrame template to fill in
    - Review past releases

    **Setup** — enter your Dataflow ID below, then expand *Save API key* to store
    your key in the system keychain (once only).
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 1. Connect
    """)
    return


@app.cell
def _(mo):
    dataflow_id_input = mo.ui.number(value=1570, label="1570", step=1)
    sandbox_toggle = mo.ui.checkbox(label="Sandbox (sandbox.reportnet.europa.eu)")
    mo.hstack([dataflow_id_input, sandbox_toggle])
    return dataflow_id_input, sandbox_toggle


@app.cell
def _(dataflow_id_input, mo, sandbox_toggle):
    _did = int(dataflow_id_input.value)
    _env = "sandbox" if sandbox_toggle.value else "production"
    key_input = mo.ui.text(
        placeholder="paste your API key here",
        kind="password",
        label="API key",
        full_width=True,
    )
    save_btn = mo.ui.run_button(label="Save to keychain")
    mo.accordion({
        f"🔑 Save API key for dataflow {_did} ({_env})": mo.vstack([
            mo.md("Saves the key to your system keychain — only needed once per dataflow."),
            key_input,
            save_btn,
        ])
    })
    return key_input, save_btn


@app.cell
def _(dataflow_id_input, key_input, mo, sandbox_toggle, save_btn):
    import reportnet as _rn
    mo.stop(not save_btn.value or not key_input.value)
    _rn.save_key(int(dataflow_id_input.value), key_input.value, sandbox=sandbox_toggle.value)
    mo.callout(mo.md("API key saved — re-run the cell above to connect."), kind="success")
    return


@app.cell
def _(dataflow_id_input, mo, sandbox_toggle):
    import reportnet

    _did = int(dataflow_id_input.value)
    _sandbox = sandbox_toggle.value
    try:
        _client = reportnet.ReportnetClient.from_keyring(_did, sandbox=_sandbox)
        _flow = _client.for_dataflow(_did)
        if not _flow.ping():
            raise reportnet.AuthError(_did, "API key invalid or revoked")
        flow = _flow
        connect_ok = True
        _env_label = "sandbox" if _sandbox else "production"
        mo.callout(mo.md(f"Connected to dataflow **{_did}** ({_env_label})"), kind="success")
    except KeyError:
        flow = None
        connect_ok = False
        mo.callout(
            mo.md(
                f"No API key found for dataflow {_did}.  \n"
                f"Expand *Save API key* above to store your key."
            ),
            kind="danger",
        )
    except reportnet.AuthError:
        flow = None
        connect_ok = False
        mo.callout(mo.md("API key is invalid or has been revoked."), kind="danger")
    return connect_ok, flow, reportnet


@app.cell
def _(mo):
    mo.md("""
    ## 2. Dataflow overview
    """)
    return


@app.cell
def _(connect_ok, flow, mo, reportnet):
    mo.stop(not connect_ok)
    info = flow.get_dataflow()
    try:
        is_big = flow.is_big_dataflow()
        backend_label = "BigData (DLT2)" if is_big else "Citus"
    except reportnet.APIError:
        backend_label = "unknown"
    mo.md(
        f"""
        | | |
        |---|---|
        | **Name** | {info.name} |
        | **Type** | {info.type} |
        | **Status** | {info.status} |
        | **Backend** | {backend_label} |
        """
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3. Dataflow structure
    """)
    return


@app.cell
def _(connect_ok, flow, mo):
    mo.stop(not connect_ok)
    with mo.status.spinner("Building diagram…"):
        _mermaid_src = flow.to_mermaid()
    mo.mermaid(_mermaid_src)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4. Find your country

    Select your country below.  The client will look up your `provider_id`
    automatically so you don't need to know it in advance.
    """)
    return


@app.cell
def _(connect_ok, flow, mo):
    import polars as pl

    mo.stop(not connect_ok)
    reporters = flow.get_reporters()
    reporting_datasets = flow.get_reporting_datasets()
    reference_datasets = flow.get_reference_datasets()

    ds_by_provider: dict = {}
    for _ds in reporting_datasets:
        ds_by_provider.setdefault(_ds.provider_id, []).append(_ds)

    reporter_table = pl.DataFrame({
        "country_code": [r.country_code or "?"  for r in reporters],
        "country_name": [r.country_name or ""   for r in reporters],
        "provider_id":  [r.provider_id           for r in reporters],
        "datasets":     [len(ds_by_provider.get(r.provider_id, [])) for r in reporters],
    })
    mo.ui.table(reporter_table)
    return ds_by_provider, pl, reference_datasets, reporters


@app.cell
def _(mo, reporters):
    country_selector = mo.ui.dropdown(
        options={
            f"{r.country_code or '?'} — {r.country_name or r.provider_id}": r.provider_id
            for r in reporters
        },
        label="Select your country",
    )
    country_selector
    return (country_selector,)


@app.cell
def _(country_selector, ds_by_provider: dict, flow, mo, reporters):
    mo.stop(country_selector.value is None)
    selected_provider_id = country_selector.value
    selected_reporter = next(r for r in reporters if r.provider_id == selected_provider_id)
    scoped = flow.for_provider(selected_provider_id)
    provider_datasets = ds_by_provider.get(selected_provider_id, [])
    mo.callout(
        mo.md(
            f"**{selected_reporter.country_name or '?'}** "
            f"(provider_id: `{selected_provider_id}`) — "
            f"**{len(provider_datasets)}** dataset(s)"
        ),
        kind="info",
    )
    return provider_datasets, scoped


@app.cell
def _(mo):
    mo.md("""
    ## 5. Datasets and tables
    """)
    return


@app.cell
def _(mo, pl, provider_datasets):
    if provider_datasets:
        ds_table = pl.DataFrame({
            "dataset_id": [ds.id        for ds in provider_datasets],
            "table_name": [ds.table_name for ds in provider_datasets],
            "status":     [ds.status    for ds in provider_datasets],
        })
        mo.ui.table(ds_table)
    else:
        mo.callout(mo.md("No datasets found for this reporter."), kind="warn")
    return


@app.cell
def _(mo, provider_datasets):
    dataset_selector = mo.ui.dropdown(
        options={ds.table_name: ds for ds in provider_datasets},
        label="Select dataset",
    )
    dataset_selector
    return (dataset_selector,)


@app.cell
def _(dataset_selector, mo):
    mo.stop(dataset_selector.value is None)
    selected_dataset = dataset_selector.value
    mo.md(
        f"**Dataset ID:** `{selected_dataset.id}`  \n"
        f"**Table:** `{selected_dataset.table_name}`  \n"
        f"**Status:** `{selected_dataset.status}`"
    )
    return (selected_dataset,)


@app.cell
def _(mo):
    mo.md("""
    ## 6. Schema — columns and types
    """)
    return


@app.cell
def _(mo, pl, scoped, selected_dataset):
    schema = scoped.get_schema(dataset_id=selected_dataset.id)
    field_rows = pl.DataFrame({
        "table":    [t.name       for t in schema.tables for f in t.fields],
        "field":    [f.name       for t in schema.tables for f in t.fields],
        "type":     [f.type.value for t in schema.tables for f in t.fields],
        "required": [f.required   for t in schema.tables for f in t.fields],
    })
    mo.vstack([
        mo.md(f"**{schema.name}** — {len(schema.tables)} table(s)"),
        mo.ui.table(field_rows),
    ])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 7. Empty DataFrame template

    `get_template()` returns one empty, fully-typed DataFrame per table.
    LINK / CODELIST columns become `pl.Enum` (polars) or `CategoricalDtype`
    (pandas), so invalid values are rejected at assignment time.

    The reference dataset is detected automatically — or pick one below to
    override.
    """)
    return


@app.cell
def _(mo, reference_datasets):
    _ref_options = {"(auto-detect)": None}
    _ref_options.update({ds.name: ds.id for ds in reference_datasets})
    ref_selector = mo.ui.dropdown(options=_ref_options, label="Reference dataset (codelists)")
    ref_selector
    return (ref_selector,)


@app.cell
def _(mo, ref_selector, scoped, selected_dataset):
    with mo.status.spinner("Building typed templates…"):
        templates = scoped.get_template(
            dataset_id=selected_dataset.id,
            ref_dataset_id=ref_selector.value,   # None = auto-detect
        )

    template = next(iter(templates.values()))
    _schema_str = {col: str(dt) for col, dt in zip(template.columns, template.dtypes)}
    mo.vstack([
        mo.md(f"**Tables:** `{list(templates)}`  —  showing `{next(iter(templates))}`"),
        mo.md(f"**Schema:** `{_schema_str}`"),
        mo.ui.table(template),
    ])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 8. Historic releases
    """)
    return


@app.cell
def _(mo, pl, scoped, selected_dataset):
    _releases = scoped.list_historic_releases(dataset_id=selected_dataset.id)
    if _releases:
        mo.ui.table(pl.DataFrame(_releases))
    else:
        mo.callout(mo.md("No releases found for this dataset."), kind="info")
    return


if __name__ == "__main__":
    app.run()
