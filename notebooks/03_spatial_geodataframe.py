import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium", app_title="Reportnet — Spatial GeoDataFrame")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(r"""
    # Spatial GeoDataFrame

    Download a spatial dataset from Reportnet and convert it to a
    **geopandas GeoDataFrame** for analysis and mapping.

    This notebook is pre-configured for dataflow **1570** (Urban Waste Water
    Treatment Directive) and France's **ProtectedArea** table, but you can
    adjust the controls below to any dataflow and country that has spatial data.

    **Requirements**

    ```bash
    uv pip install reportnet-client[spatial]
    # or: pip install reportnet-client[spatial]
    ```

    **Setup** — enter your Dataflow ID and country code below, then expand
    *Save API key* to store your key in the system keychain (once only).
    The API key must have **export** rights for the dataflow.
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
    dataflow_id_input = mo.ui.number(value=1570, label="Dataflow ID", step=1)
    country_code_input = mo.ui.text(value="FR", label="Country code (ISO 3166-1 α-2)")
    sandbox_input = mo.ui.checkbox(label="Sandbox (sandbox.reportnet.europa.eu)")
    mo.hstack([dataflow_id_input, country_code_input, sandbox_input])
    return country_code_input, dataflow_id_input, sandbox_input


@app.cell
def _(dataflow_id_input, mo, sandbox_input):
    _did = int(dataflow_id_input.value)
    _env = "sandbox" if sandbox_input.value else "production"
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
def _(dataflow_id_input, key_input, mo, sandbox_input, save_btn):
    import reportnet as _rn
    mo.stop(not save_btn.value or not key_input.value)
    _rn.save_key(int(dataflow_id_input.value), key_input.value, sandbox=sandbox_input.value)
    mo.callout(mo.md("API key saved — re-run the cell above to connect."), kind="success")
    return


@app.cell
def _(country_code_input, dataflow_id_input, mo, sandbox_input):
    import reportnet

    _did = int(dataflow_id_input.value)
    _cc = country_code_input.value.strip().upper()
    _sandbox = sandbox_input.value

    try:
        _client = reportnet.ReportnetClient.from_keyring(_did, sandbox=_sandbox)
        _base_flow = _client.for_dataflow(_did)
        flow = _base_flow.find_reporter(_cc)
        connect_ok = True
        _env_label = "sandbox" if _sandbox else "production"
        mo.callout(
            mo.md(f"Connected as **{_cc}** on dataflow **{_did}** ({_env_label})"),
            kind="success",
        )
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
    except ValueError as _e:
        flow = None
        connect_ok = False
        mo.callout(mo.md(f"Country lookup failed: {_e}"), kind="danger")
    except reportnet.AuthError:
        flow = None
        connect_ok = False
        mo.callout(mo.md("API key is invalid or has been revoked."), kind="danger")
    return connect_ok, flow, reportnet


@app.cell
def _(mo):
    mo.md("""
    ## 2. Select spatial dataset
    """)
    return


@app.cell
def _(connect_ok, flow, mo):
    import polars as pl

    mo.stop(not connect_ok)

    # Find datasets that contain at least one geometry-typed field
    _GEOM_TYPES = {
        "POINT", "LINESTRING", "POLYGON",
        "MULTIPOINT", "MULTILINESTRING", "MULTIPOLYGON",
    }
    _datasets = flow.get_reporting_datasets()
    _spatial = []
    for _ds in _datasets:
        try:
            _schema = flow.get_schema(dataset_id=_ds.id)
            _geom_fields = [
                f.name
                for t in _schema.tables
                for f in t.fields
                if f.type.value in _GEOM_TYPES
            ]
            if _geom_fields:
                _spatial.append((_ds, _geom_fields))
        except Exception:
            pass

    if not _spatial:
        mo.stop(True, mo.callout(mo.md("No spatial datasets found for this country."), kind="warn"))

    spatial_datasets = _spatial
    mo.callout(
        mo.md(
            f"Found **{len(_spatial)}** spatial dataset(s):  \n"
            + "  \n".join(
                f"- `{ds.table_name}` (id {ds.id}) — geometry columns: `{fields}`"
                for ds, fields in _spatial
            )
        ),
        kind="info",
    )
    return pl, spatial_datasets


@app.cell
def _(mo, spatial_datasets):
    dataset_selector = mo.ui.dropdown(
        options={ds.table_name: (ds, fields) for ds, fields in spatial_datasets},
        label="Select spatial dataset",
    )
    dataset_selector
    return (dataset_selector,)


@app.cell
def _(dataset_selector, mo):
    mo.stop(dataset_selector.value is None)
    selected_ds, geom_fields = dataset_selector.value
    geometry_col_selector = mo.ui.dropdown(
        options=geom_fields,
        label="Geometry column",
    )
    mo.hstack([
        mo.md(f"**Dataset ID:** `{selected_ds.id}`  —  **status:** `{selected_ds.status}`"),
        geometry_col_selector,
    ])
    return geometry_col_selector, selected_ds


@app.cell
def _(mo):
    mo.md("""
    ## 3. Export
    """)
    return


@app.cell
def _(mo):
    export_btn = mo.ui.run_button(label="Export dataset")
    export_btn
    return (export_btn,)


@app.cell
def _(connect_ok, export_btn, flow, mo, selected_ds):
    mo.stop(not connect_ok or not export_btn.value)

    with mo.status.spinner(f"Exporting dataset {selected_ds.id}…"):
        _handle = flow.etl_export(dataset_id=selected_ds.id)
        raw_frames = _handle.to_frames(poll_interval=5.0, timeout=300.0)

    _counts = "  \n".join(
        f"- **{name}**: {df.shape[0]:,} rows × {df.shape[1]} cols"
        for name, df in raw_frames.items()
    )
    mo.callout(mo.md(f"Export complete:  \n{_counts}"), kind="success")
    return (raw_frames,)


@app.cell
def _(mo):
    mo.md("""
    ## 4. Convert to GeoDataFrame
    """)
    return


@app.cell
def _(geometry_col_selector, mo, raw_frames, reportnet):
    mo.stop(geometry_col_selector.value is None)

    # raw_frames is keyed by table schema name (e.g. "ProtectedArea"), not the
    # dataset display name (e.g. "Spatial data") — use the first exported table.
    _geom_col = geometry_col_selector.value
    _frame_key = next(iter(raw_frames))
    _frame = raw_frames[_frame_key]

    try:
        gdf = reportnet.to_geodataframe(_frame, _geom_col)
        mo.callout(
            mo.md(
                f"**{_frame_key}** → GeoDataFrame  \n"
                f"{gdf.shape[0]:,} rows × {gdf.shape[1]} cols  —  "
                f"CRS: `{gdf.crs}`  —  "
                f"geometry column: `{gdf.geometry.name}`"
            ),
            kind="success",
        )
    except ImportError as _e:
        gdf = None
        mo.stop(
            True,
            mo.callout(
                mo.md(f"**{_e}**  \nInstall with: `pip install reportnet-client[spatial]`"),
                kind="danger",
            ),
        )
    return (gdf,)


@app.cell
def _(gdf, mo, pl):
    # Drop the geometry column for display (it's long WKT / GeoJSON)
    _display = pl.from_pandas(gdf.drop(columns=gdf.geometry.name).head(20))
    mo.vstack([
        mo.md("**Preview** (first 20 rows, geometry column hidden):"),
        mo.ui.table(_display),
    ])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5. Map
    """)
    return


@app.cell
def _(gdf, mo):
    import matplotlib.pyplot as plt

    _valid = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if _valid.empty:
        mo.callout(mo.md("No non-null geometries to plot."), kind="warn")
    else:
        _fig, _ax = plt.subplots(figsize=(10, 6))
        _valid.plot(ax=_ax, color="steelblue", edgecolor="white", linewidth=0.4, alpha=0.7)
        _ax.set_title(f"{gdf.geometry.name}  ({len(_valid):,} features)")
        _ax.set_xlabel("Longitude")
        _ax.set_ylabel("Latitude")
        plt.tight_layout()
        mo.pyplot(_fig)
    return


if __name__ == "__main__":
    app.run()
