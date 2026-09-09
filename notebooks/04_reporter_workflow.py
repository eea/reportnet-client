import marimo

__generated_with = "0.23.6"
app = marimo.App(width="medium", app_title="Reportnet — Reporter Workflow")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(r"""
    # Reporter workflow — from a CSV on disk to a validated upload

    The everyday job of a reporter: you have a spreadsheet, Reportnet has a
    schema, and the two disagree in small ways. This notebook walks the whole
    cycle on **dataflow 2003** (*UWWTD — TESTING — BIG DATA*) as the Italian
    reporter:

    1. **Connect** as a reporter
    2. **Read the schema** for the table you're filling in
    3. **Load your CSV** — everything arrives as text
    4. **Compare it to the schema** — types *and* code lists
    5. **Fix what's wrong** in polars
    6. **Upload** to Reportnet
    7. **Validate** and read what the server says

    The sample file `data/industries.csv` has two deliberate mistakes of the
    kind that actually happen: a number typed as a word, and a code-list value
    that looks right but isn't. Both are caught **before** anything is uploaded.

    > Reportnet has no release endpoint. This notebook prepares and validates a
    > submission; a human still presses **Release** in the web UI.
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
    key_input = mo.ui.text(
        placeholder="paste your reporter API key (optional)",
        kind="password",
        label="API key",
        full_width=True,
    )
    mo.vstack([
        mo.md("""
        """),
        key_input,
    ])
    return (key_input,)


@app.cell
def _(key_input, mo):
    import reportnet

    DATAFLOW_ID = 2003
    COUNTRY_CODE = "IT"

    _pasted = key_input.value.strip()
    if _pasted:
        # find_reporter() resolves the country code to a provider_id for us.
        _client = reportnet.ReportnetClient(api_key=_pasted)
        try:
            flow = _client.for_dataflow(DATAFLOW_ID).find_reporter(COUNTRY_CODE)
            connect_error = None
        except Exception as _exc:
            flow, connect_error = None, f"{type(_exc).__name__}: {_exc}"
    else:
        flow, connect_error = reportnet.connect_interactive(
            DATAFLOW_ID, country_code=COUNTRY_CODE
        )

    connect_ok = flow is not None
    mo.callout(
        mo.md(
            f"Connected to dataflow **{DATAFLOW_ID}** as **{COUNTRY_CODE}** "
            f"(provider `{flow._provider_id}`)"
        ),
        kind="success",
    ) if connect_ok else mo.callout(mo.md(connect_error or "Not connected"), kind="danger")
    return connect_ok, flow, reportnet


@app.cell
def _(connect_ok, flow, mo):
    mo.stop(not connect_ok)

    # A reporter key is 403 on the unscoped dataflow read, so capabilities()
    # reports that reads have to carry the provider id. The client does that
    # for you — this is here so you can see what it inferred.
    mo.md(f"`{flow.capabilities().summary()}`")
    return


@app.cell
def _(mo):
    mo.md("""
    ## 2. Find the dataset and read its schema

    A reporter sees only its own datasets. Dataflow 2003 gives Italy two:
    *Descriptive data* and *Spatial data*. We're filling in the **Industries**
    table of the descriptive one.
    """)
    return


@app.cell
def _(connect_ok, flow, mo):
    mo.stop(not connect_ok)

    my_datasets = flow.get_reporting_datasets()
    mo.md("  \n".join(f"- `{d.id}` — **{d.table_name}**" for d in my_datasets))
    return (my_datasets,)


@app.cell
def _(connect_ok, flow, mo, my_datasets):
    mo.stop(not connect_ok)

    dataset = next(d for d in my_datasets if "Descriptive" in d.table_name)
    schema = flow.get_schema(dataset_id=dataset.id)
    table = schema.table("Industries")

    import polars as pl

    schema_view = pl.DataFrame({
        "field": [f.name for f in table.fields],
        "type": [f.type.value for f in table.fields],
        "required": [f.required for f in table.fields],
        "description": [f.description for f in table.fields],
    })
    mo.vstack([
        mo.md(f"**{dataset.table_name}** (`{dataset.id}`) → table **{table.name}**"),
        schema_view,
    ])
    return dataset, pl, table


@app.cell
def _(mo):
    mo.md("""
    ## 3. Load the CSV

    `infer_schema_length=0` keeps every column as text. That is deliberate: we
    want to see exactly what is in the file, not what polars guesses it meant.
    A CSV has no types, so *every* type question is still open at this point.
    """)
    return


@app.cell
def _(mo, pl):
    from pathlib import Path

    csv_path = Path(__file__).parent / "data" / "industries.csv"
    raw = pl.read_csv(csv_path, infer_schema_length=0)
    mo.vstack([mo.md(f"`{csv_path.name}` — {raw.height} rows, all columns `String`"), raw])
    return (raw,)


@app.cell
def _(mo):
    mo.md("""
    ## 4. Compare the file to the schema

    Two different questions, two different checks:

    - **Types** — can each value become what the schema says it is? A
      `NUMBER_INTEGER` column holding `"one"` cannot.
    - **Code lists** — is each `LINK` / `CODELIST` value one the dataflow
      actually accepts? `get_codelists()` answers this by exporting the
      reference dataset the schema points at.

    Neither check needs to touch your data twice, and both run before a single
    byte is uploaded.
    """)
    return


@app.cell
def _(connect_ok, dataset, flow, mo):
    mo.stop(not connect_ok)

    # The Industries LINK fields reference the *descriptive* codelist dataset.
    # Pick the reference dataset by name rather than by list position — the
    # order is not stable, and the spatial codelist would resolve nothing here.
    reference = next(
        r for r in flow.get_reference_datasets() if "Descriptive codelist" in r.name
    )

    with mo.status.spinner("Exporting the reference dataset to resolve code lists…"):
        codelists = flow.get_codelists(
            dataset_id=dataset.id, ref_dataset_id=reference.id, timeout=600.0
        )

    mo.md(
        f"Resolved **{len(codelists)}** code lists from *{reference.name}* "
        f"(`{reference.id}`), including:  \n"
        + "  \n".join(
            f"- `{name}` → {sorted(codelists[name])[:8]}"
            for name in ("indState", "indBranch")
            if name in codelists
        )
    )
    return (codelists,)


@app.cell
def _(pl, reportnet):
    # polars dtype to cast each schema type to. Anything not listed here stays
    # text, which is what Reportnet stores it as anyway.
    _CASTS = {
        reportnet.FieldType.NUMBER_INTEGER: pl.Int64,
        reportnet.FieldType.NUMBER_DECIMAL: pl.Float64,
        reportnet.FieldType.DATE: pl.Date,
    }

    def type_errors(frame, table):
        """Values that cannot become the type the schema asks for.

        cast_frame() raises on the first bad column; this reports every one of
        them at once, which is what you want when reviewing a file by hand.
        """
        problems = []
        for field in table.fields:
            target = _CASTS.get(field.type)
            if target is None or field.name not in frame.columns:
                continue
            column = frame[field.name]
            bad = frame.filter(
                column.is_not_null() & column.cast(target, strict=False).is_null()
            )[field.name].to_list()
            if bad:
                problems.append(
                    f"`{field.name}` expects **{field.type.value}** but has {bad}"
                )
        return problems

    return (type_errors,)


@app.cell
def _(codelists, connect_ok, mo, raw, table, type_errors):
    mo.stop(not connect_ok)

    found = type_errors(raw, table) + [
        f"{e}" for e in table.validate_frame(raw, codelists=codelists)
    ]
    mo.callout(
        mo.md("**Problems found before upload:**  \n"
              + "  \n".join(f"{i}. {p}" for i, p in enumerate(found, 1))),
        kind="warn" if found else "success",
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5. Fix them

    Two ordinary polars edits. `IT-IND-003` had its organic load typed out as a
    word, and `IT-IND-002` used `BEER` where the code list says `BREW`.

    Nothing clever here on purpose — the point is that the errors were found on
    your machine, in seconds, instead of surfacing as a rejected submission
    weeks later.
    """)
    return


@app.cell
def _(pl, raw, table):
    fixed = raw.with_columns(
        pl.col("indOrganicLoad").replace({"one": "1"}),
        pl.col("indBranch").replace({"BEER": "BREW"}),
    )
    # Now that the values are right, cast the whole frame to the schema's types.
    # cast_frame() raises if anything still doesn't fit, so this is also a check.
    typed = table.cast_frame(fixed)
    typed
    return (typed,)


@app.cell
def _(codelists, connect_ok, mo, table, type_errors, typed):
    mo.stop(not connect_ok)

    remaining = type_errors(typed, table) + table.validate_frame(typed, codelists=codelists)
    mo.callout(
        mo.md("**Clean** — every value matches the schema's types and code lists."
              if not remaining else
              "**Still wrong:**  \n" + "  \n".join(f"- {r}" for r in remaining)),
        kind="success" if not remaining else "danger",
    )
    return (remaining,)


@app.cell
def _(mo):
    mo.md("""
    ## 6. Upload

    `replace=True` replaces the rows in this one table rather than appending —
    rerun the notebook and you get four rows, not eight. Uploading is a real
    write to production, so it is behind a button.
    """)
    return


@app.cell
def _(connect_ok, mo, remaining):
    mo.stop(not connect_ok)
    upload_btn = mo.ui.run_button(label="Upload Industries to Reportnet")
    mo.vstack([
        mo.md("Nothing is sent until you click." if not remaining else
              "Fix the problems above first."),
        upload_btn,
    ])
    return (upload_btn,)


@app.cell
def _(connect_ok, dataset, flow, mo, remaining, typed, upload_btn):
    mo.stop(not connect_ok or not upload_btn.value or bool(remaining))

    with mo.status.spinner("Uploading…"):
        flow.import_frames(
            dataset_id=dataset.id,
            frames={"Industries": typed},
            replace=True,
            timeout=600.0,
        )

    upload_done = True
    mo.callout(mo.md(f"Uploaded **{typed.height}** rows to **Industries**."), kind="success")
    return (upload_done,)


@app.cell
def _(mo):
    mo.md("""
    ## 7. Validate

    Local checks cannot run Reportnet's own rules — those are SQL expressions
    held server-side, and they see the **whole dataset**, not just your table.
    That is the whole point of this step: it finds what no amount of local
    checking can.

    `validate()` submits one job and then polls its status. Two things about
    that are worth knowing before you run it:

    - It can take **many minutes** on a shared dataflow. The job queues behind
      everyone else's.
    - **Never resubmit while one is running.** Reportnet answers a second
      submission with HTTP 423, and every rejected attempt shows up as a red
      error banner in the Reportnet web UI for whoever is looking at it.

    The next cell therefore submits once, and if the job outlives its timeout it
    reads the published results instead of asking again.
    """)
    return


@app.cell
def _(connect_ok, mo, upload_done):
    mo.stop(not connect_ok or not upload_done)
    validate_btn = mo.ui.run_button(label="Run validation")
    validate_btn
    return (validate_btn,)


@app.cell
def _(connect_ok, dataset, flow, mo, reportnet, validate_btn):
    mo.stop(not connect_ok or not validate_btn.value)

    with mo.status.spinner("Validating — this can take several minutes…"):
        try:
            result = flow.validate(dataset_id=dataset.id, poll_interval=10.0, timeout=1200.0)
            _how = "job reported FINISHED"
        except reportnet.JobTimeoutError:
            # The orchestrator can still report IN_PROGRESS after the results
            # have been published. Read them rather than submitting again —
            # a second submission is a 423 and an error banner in the web UI.
            result = flow.get_validation_results(dataset_id=dataset.id)
            _how = "job still running; read the published results instead"

    mo.md(f"**{result.summary()}**  \n_{_how}_")
    return (result,)


@app.cell
def _(mo):
    mo.md("""
    ### Reading the result

    Reportnet groups its findings: one row per *rule that fired*, with
    `record_count` saying how many of your records it fired on. So a single
    line can stand for every row in the table.

    Four levels, in descending severity: `BLOCKER`, `ERROR`, `WARNING`, `INFO`.
    Only a `BLOCKER` stops a release.
    """)
    return


@app.cell
def _(mo, result):
    mo.stop(result is None)

    _levels = ("BLOCKER", "ERROR", "WARNING", "INFO")
    _counts = {lvl: sum(1 for i in result.issues if i.level == lvl) for lvl in _levels}
    mo.vstack([
        mo.md("  ".join(f"**{lvl}**: {n}" for lvl, n in _counts.items() if n)
              or "**No issues.**"),
        result.to_frame() if result.issues else mo.md(""),
    ])
    return


@app.cell
def _(mo):
    mo.md(r"""
    ### What the remaining issue means

    On a run of this notebook the result was a single grouped issue:

    | | |
    |---|---|
    | Level | `ERROR` — not a `BLOCKER`, so it does not stop a release |
    | Table / field | `Industries` · `repCode` |
    | Rule | `RelationalTest-12-Industries` |
    | Message | *Data in the dataset are not coherent* |
    | Records | 4 — every row we uploaded |

    **This is not a mistake in our four rows.** `repCode` is the report
    identifier that ties the whole dataset together: fourteen of the fifteen
    tables carry it, and `ReportPeriod` is the table that declares which report
    periods exist. We uploaded `Industries` with `repCode = "IT2026"` while
    `ReportPeriod` is still **empty**, so there is no report period for those
    rows to belong to. The rule is doing its job.

    That is the shape of a *relational* rule, and the reason this step cannot be
    skipped: every local check in section 4 passed, because each looked at one
    column of one table. Only the server sees that `Industries.repCode` has
    nothing to join to. Fill in `ReportPeriod` and this clears.

    So: two errors caught on your laptop in seconds, one caught by the server
    that no local check could have found. That is the division of labour to
    expect.
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## What happens next

    Validation results are advice, not a gate — nothing here submits anything.
    When the issues you own are cleared, open the dataflow in the Reportnet web
    UI and press **Release**. There is no API endpoint for that step.

    Two things worth carrying to your own data:

    - **Check code lists against the reference dataset the schema points at**,
      chosen by name. Picking one by list position is how you end up validating
      against the wrong list and resolving nothing.
    - **Do the type and code-list checks locally first.** They cost seconds and
      catch the errors that would otherwise come back as a rejected submission.

    For the one-call version of this whole cycle — preflight, baseline export,
    upload, full readback comparison, then validation — see
    `DataflowClient.prepare_submission()`.
    """)
    return


if __name__ == "__main__":
    app.run()
