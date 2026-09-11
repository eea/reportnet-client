# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "marimo>=0.24.1",
# ]
# ///
import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium", app_title="Reportnet — Reporter workflow")


@app.cell
def _():
    import marimo as mo

    # Paths must resolve against the notebook, not the working directory —
    # CI exports these from the repo root, where "data/" does not exist.
    HERE = mo.notebook_dir()
    return HERE, mo


@app.cell
def _(mo):
    mo.md(r"""
    # Upload and validate a report

    Five steps, start to finish, as the **French reporter on dataflow 2003**
    (*UWWTD — TESTING — BIG DATA*):

    | | | |
    |---|---|---|
    | 1 | **Connect** | a reporter key, scoped to France |
    | 2 | **Look** | which dataset, what tables |
    | 3 | **Load** | the Toulon data, exactly as it comes off disk |
    | 4 | **Upload** | `import_frames` reshapes it to the schema |
    | 5 | **Validate** | and read what the server says |

    The example data is the **Toulon subset** — 15 agglomerations and 15
    treatment plants around Toulon, extracted from France's 2022 submission.
    Small enough to read, real enough to fail in realistic ways.

    > Reportnet has no release endpoint. This prepares and validates a
    > submission; a human still presses **Release** in the web UI.
    """)
    return


@app.cell
def _(HERE, mo):
    mo.image(
        HERE / "images/toulon_subset_map.png",
        alt="Map of the Toulon subset: 15 agglomerations, 15 treatment plants, "
            "and the Gapeau sensitive area",
        caption="What we are about to upload. Circles are agglomerations (where the "
                "waste water comes from), squares are treatment plants, green is the "
                "Gapeau catchment — a sensitive area, so its plants face stricter limits.",
        width=900,
    )
    return


@app.cell
def _(mo):
    mo.md("""## 1. Connect""")
    return


@app.cell
def _(mo):
    key_input = mo.ui.text(
        placeholder="paste your France reporter API key",
        kind="password",
        label="API key",
        full_width=True,
    )
    key_input
    return (key_input,)


@app.cell
def _(key_input, mo):
    import reportnet

    DATAFLOW_ID = 2003
    COUNTRY = "FR"

    _key = key_input.value.strip()
    flow = None
    connect_error = None
    if _key:
        try:
            # find_reporter() turns the country code into the provider_id that
            # every reporter request has to carry.
            flow = reportnet.ReportnetClient(api_key=_key).for_dataflow(
                DATAFLOW_ID
            ).find_reporter(COUNTRY)
        except Exception as _exc:
            connect_error = _exc

    mo.md(
        f"Connected as **{COUNTRY}** on dataflow **{DATAFLOW_ID}** "
        f"(provider `{flow._provider_id}`)."
        if flow is not None
        else f"Could not connect: `{connect_error}`"
        if connect_error
        else "*Paste a key above to run against the live API. "
        "The rest of the notebook explains each step either way.*"
    )
    return DATAFLOW_ID, flow, reportnet


@app.cell
def _(mo):
    mo.md(r"""
    ### Your key decides what you can do

    A Reportnet key carries a **role**, not just an identity — and the same
    person can hold several. A key made as a custodian has no reporter rights
    even if you are also a lead reporter, and regenerating it does not help.

    One read tells you which you have:

    | | custodian key | reporter key |
    |---|---|---|
    | `GET /dataflow/v1/{id}` unscoped | ✅ 200 | ❌ 403 |
    | the same with `providerId` | ❌ 403 | ✅ 200 |

    The requirement is *inverted*, so sending `providerId` always is not a fix.
    `find_reporter()` and `capabilities()` work this out for you; you only need
    to know that **uploading report data needs a reporter key**.
    """)
    return


@app.cell
def _(flow, mo):
    caps = flow.capabilities() if flow is not None else None
    mo.md(
        f"`capabilities()` → **{caps.role}** key"
        if caps
        else "*(connect above to probe the key's role)*"
    )
    return


@app.cell
def _(mo):
    mo.md("""## 2. Which dataset am I filling in?""")
    return


@app.cell
def _(flow, mo):
    import polars as pl

    if flow is not None:
        _rows = [
            {"dataset_id": d.id, "table": d.table_name, "status": d.status}
            for d in flow.get_reporting_datasets()
        ]
        datasets = pl.DataFrame(_rows)
        _out = mo.vstack([
            mo.md("France has one reporting dataset per schema:"),
            mo.ui.table(datasets, selection=None),
        ])
    else:
        datasets = None
        _out = mo.md("*(connect to list your datasets)*")
    _out
    return (pl,)


@app.cell
def _(mo):
    mo.md(r"""
    We want **Descriptive data** — the tabular half (`108952` for France).
    Spatial data is a separate dataset with its own notebook.

    `get_schema()` returns the tables and their fields. This is the shape your
    upload has to match.
    """)
    return


@app.cell
def _(flow, mo, pl):
    DATASET_ID = 108952

    if flow is not None:
        schema = flow.get_schema(dataset_id=DATASET_ID)
        _t = pl.DataFrame([
            {
                "table": t.name,
                "fields": len(t.fields),
                "required": len(t.required_columns()),
            }
            for t in schema.tables
        ])
        _out = mo.ui.table(_t, selection=None)
    else:
        schema = None
        _out = mo.md("*(connect to read the schema)*")
    _out
    return DATASET_ID, schema


@app.cell
def _(mo):
    mo.md("""## 3. Load the data — as it comes off disk""")
    return


@app.cell
def _(HERE, mo, pl):
    frames = {}
    for _path in sorted((HERE / "data" / "toulon").glob("*.parquet")):
        _name = _path.stem
        _df = pl.read_parquet(_path)
        if len(_df):
            frames[_name] = _df

    mo.vstack([
        mo.md(
            f"**{len(frames)} tables, {sum(len(f) for f in frames.values())} rows.** "
            "No cleaning, no renaming, no reordering — this is the raw extract."
        ),
        mo.ui.table(
            pl.DataFrame([
                {"table": k, "rows": len(v), "columns": v.width}
                for k, v in frames.items()
            ]),
            selection=None,
        ),
    ])
    return (frames,)


@app.cell
def _(mo):
    mo.md(r"""
    ### It does not match the schema, and that is normal

    Reportnet rejects an import whose header is not **exactly** the table's
    field list. Not a superset, not a subset — exactly. Real extracts never
    arrive that way:

    - they carry **extra** columns from whatever produced them
      (`countryCode`, `snapshotId`, `aggBeginLife_original`)
    - they are **missing** fields the source never had
    - dates arrive as timestamps, and a `DATE` field rejects a time part

    Get it wrong and the upload returns **HTTP 200**, then the *job* fails with
    *"Import files contain incorrect headers."* — so the request looked fine and
    the data never landed.

    `import_frames` handles all of it. The next cell shows what it will change,
    before anything is sent.
    """)
    return


@app.cell
def _(frames, mo, pl, schema):
    if schema is not None:
        from reportnet._util import align_frame

        _rows = []
        for _name, _df in frames.items():
            _table = next(
                (t for t in schema.tables if t.name.lower() == _name.lower()), None
            )
            if _table is None:
                continue
            _, _added, _dropped = align_frame(_table, _df)
            _required = set(_table.required_columns())
            _rows.append({
                "table": _name,
                "dropped": len(_dropped),
                "added empty": len(_added),
                "…of which required": ", ".join(c for c in _added if c in _required) or "—",
            })
        _out = mo.vstack([
            mo.md("What alignment will do to each table:"),
            mo.ui.table(pl.DataFrame(_rows), selection=None),
            mo.md(
                "`repCode` is the one to notice. It is **required in every "
                "table** and missing from most of the extract — and alignment "
                "can only fix *shape*, never invent a *value*. Left empty it "
                "uploads fine and fails validation later, so we supply it."
            ),
        ])
    else:
        _out = mo.md("*(connect to compare the data against the schema)*")
    _out
    return


@app.cell
def _(frames, pl):
    # repCode is the key every table joins back to ReportPeriod on, and its
    # first two characters must be the ISO country code.
    ready = {
        name: (
            df.drop("repCode") if "repCode" in df.columns else df
        ).with_columns(pl.lit("FR").alias("repCode"))
        for name, df in frames.items()
    }
    return (ready,)


@app.cell
def _(mo):
    mo.md("""## 4. Upload""")
    return


@app.cell
def _(mo):
    run_upload = mo.ui.run_button(label="Upload to Reportnet")
    mo.vstack([
        mo.md(
            "`replace=True` clears each table first, so re-running is safe. "
            "Ten tables, uploaded and polled one at a time — about 3 minutes."
        ),
        run_upload,
    ])
    return (run_upload,)


@app.cell
def _(DATASET_ID, flow, mo, ready, run_upload):
    mo.stop(not run_upload.value or flow is None, mo.md("*(not run yet)*"))

    flow.import_frames(dataset_id=DATASET_ID, frames=ready, replace=True, timeout=600)
    mo.md("**Upload finished.** Every table reported FINISHED.")
    return


@app.cell
def _(DATASET_ID, flow, mo, pl, run_upload):
    mo.stop(not run_upload.value or flow is None, mo.md(""))

    _landed = [
        {"table": t, "rows": i["records"]}
        for t, i in (flow.verify_import(dataset_id=DATASET_ID) or {}).items()
        if i.get("records")
    ]
    mo.vstack([
        mo.md("`verify_import()` reads back what actually landed:"),
        mo.ui.table(pl.DataFrame(_landed), selection=None),
    ])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 5. Validate

    Validation runs the dataflow's quality rules server-side — 433 of them on
    this dataset. It is slow: **10–20 minutes** is normal here, and the client's
    default timeout is shorter than that.

    If it times out, **do not submit again.** Reportnet answers a second
    submission with a 423 and an error banner in the reporter's UI. Poll
    `get_validation_results()` instead — it starts nothing.
    """)
    return


@app.cell
def _(mo):
    run_validate = mo.ui.run_button(label="Validate")
    run_validate
    return (run_validate,)


@app.cell
def _(DATASET_ID, flow, mo, run_validate):
    mo.stop(not run_validate.value or flow is None, mo.md("*(not run yet)*"))

    job = flow.add_validation_job(dataset_id=DATASET_ID)
    mo.md(
        f"Validation job **{job.job_id}** submitted. "
        "Re-run the next cell until it reports FINISHED — "
        "submitting again would be refused."
    )
    return


@app.cell
def _(DATASET_ID, flow, mo, run_validate):
    mo.stop(not run_validate.value or flow is None, mo.md(""))

    result = flow.get_validation_results(dataset_id=DATASET_ID)
    mo.md(
        f"**Stale — do not read these yet.** {result.summary()}"
        if result.is_stale
        else f"{result.summary()}"
    )
    return (result,)


@app.cell
def _(mo):
    mo.md(r"""
    ### Results can be stale, and look exactly like fresh ones

    The results endpoint returns **no timestamp and no run id**, and Reportnet
    does not clear it while a new run is going — it keeps serving the *previous*
    run's numbers. Identical totals from changed data is the whole failure mode:
    there is nothing in the response to notice.

    So `ValidationResult` carries where the numbers came from:

    - `job` — the run that produced them
    - `superseded_by` — a validation running right now
    - `data_changed_at` — when the data was last imported
    - `is_stale` — true if either applies

    **Check `is_stale` before believing a number.**
    """)
    return


@app.cell
def _(mo, result, run_validate):
    mo.stop(not run_validate.value, mo.md(""))

    mo.md(f"""
    | | |
    |---|---|
    | results from | job `{result.job.id if result.job else "?"}` |
    | that run finished | `{result.job.status_changed_at if result.job else "?"}` |
    | data last imported | `{result.data_changed_at}` |
    | a run in flight | `{result.superseded_by.id if result.superseded_by else "none"}` |
    | **stale** | **`{result.is_stale}`** |
    """)
    return


@app.cell
def _(mo):
    mo.md("""### Reading the issues""")
    return


@app.cell
def _(HERE, mo):
    mo.image(
        HERE / "images/validation_results.png",
        alt="Bar chart of the eight rules that fired, by severity and records flagged",
        caption="A representative run: 8 rules fired over 50 records. Severity is "
                "ordered BLOCKER → ERROR → WARNING; the bar is how many records "
                "each rule flagged.",
        width=900,
    )
    return


@app.cell
def _(mo, pl, result, run_validate):
    mo.stop(not run_validate.value, mo.md("*(validate to see your own issues)*"))

    _rows = [
        {
            "severity": i.level,
            "table": i.table,
            "field": i.field or "—",
            "records": i.record_count,
            "rule": i.short_code,
            "message": i.message,
        }
        for i in sorted(result.issues, key=lambda x: x.level)
    ]
    mo.ui.table(pl.DataFrame(_rows), selection=None) if _rows else mo.md("No issues.")
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### What those issues mean here

    Most of them are the *subset*, not a data problem:

    - **`TB461` / `TB463` Reporter, Contacts** — mandatory tables the Toulon
      extract has no source for, so they are empty.
    - **`ReportPeriod-1-repReferenceSystem`** — a required field the source
      does not carry. Alignment added the column; only you can supply a value.
    - **`UWWTPs-31`** flags all 15 plants although its message says *"over
      100 000 p.e."*, and only one plant is that big. Its SQL is
      `A AND B AND C OR D` with no parentheses, so `OR D` applies to every row.
      That is a **bug in the rule**, not in the data — worth reporting to the
      dataflow's custodian rather than trying to fix locally.

    Which is the real lesson: a failing rule is a question, not a verdict.

    ### Next

    **BLOCKER** stops a release; **ERROR** and **WARNING** do not. Fix what is
    real, re-upload, re-validate, then press **Release** in the web UI — the
    API has no endpoint for it.
    """)
    return


if __name__ == "__main__":
    app.run()
