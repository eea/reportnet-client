"""Presentation helpers — rendering dataflow structure as diagrams.

Kept separate from the client layers: these functions take already-fetched
models and perform no network I/O, so they can be tested and reused without
an API key.
"""

from __future__ import annotations

from collections import defaultdict

from .models import DataflowInfo, ReferenceDataset, ReportingDataset, TestDataset
from .providers import by_id as provider_by_id

# Worst-status priority order (higher value = worse)
_STATUS_RANK = {
    "FINAL": 0,
    "TECHNICALLY_ACCEPTED": 1,
    "PENDING": 2,
    "CORRECTION_REQUESTED": 3,
}

_STATUS_COLOR = {
    "FINAL":                 ("#A8D5A2", "#1a3a1a"),
    "TECHNICALLY_ACCEPTED":  ("#C8E6C9", "#1a3a1a"),
    "PENDING":               ("#D0D0D0", "#333333"),
    "CORRECTION_REQUESTED":  ("#FFD580", "#333333"),
}


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("#", "#35;")
    )


def dataflow_to_mermaid(
    info: DataflowInfo,
    *,
    reporting_datasets: tuple[ReportingDataset, ...] | list[ReportingDataset] = (),
    reference_datasets: tuple[ReferenceDataset, ...] | list[ReferenceDataset] = (),
    test_datasets: tuple[TestDataset, ...] | list[TestDataset] = (),
) -> str:
    """Render a dataflow's structure as a Mermaid ``graph LR`` string.

    One compact node per reporter country, coloured by their worst submission
    status across all tables (green = all FINAL, yellow = correction requested,
    grey = pending).  Reference and test datasets are shown as separate nodes
    connected to the dataflow.

    Pure function — pass in already-fetched models.  Most callers want
    :meth:`~reportnet.DataflowClient.to_mermaid`, which fetches for you.

    Renders natively in marimo without any CLI tools::

        mo.mermaid(flow.to_mermaid())
    """
    lines: list[str] = ["graph LR"]

    # ── Dataflow ──────────────────────────────────────────────────────────
    df_label = (
        f"{_esc(info.name)}<br/>"
        f"<small>id={info.id} · {_esc(info.type)} · {_esc(info.status)}</small>"
    )
    lines.append(f'    df[["{df_label}"]]')
    lines.append("    style df fill:#2C5F8A,color:#fff,stroke:#1a3f63")
    lines.append("")

    # ── Reference datasets ────────────────────────────────────────────────
    for rd in reference_datasets:
        nid = f"ref_{rd.id}"
        lines.append(f'    {nid}["{_esc(rd.name)}"]')
        lines.append(f"    style {nid} fill:#4CAF50,color:#fff,stroke:#388E3C")
        lines.append(f"    df -->|ref| {nid}")
    if reference_datasets:
        lines.append("")

    # ── Test datasets ─────────────────────────────────────────────────────
    for td in test_datasets:
        nid = f"test_{td.id}"
        lines.append(f'    {nid}["{_esc(td.name)}"]')
        lines.append(f"    style {nid} fill:#FF9800,color:#fff,stroke:#E65100")
        lines.append(f"    df -.->|test| {nid}")
    if test_datasets:
        lines.append("")

    # ── One node per reporter — coloured by worst status ──────────────────
    by_provider: dict[int, list[ReportingDataset]] = defaultdict(list)
    for ds in reporting_datasets:
        by_provider[ds.provider_id].append(ds)

    for provider_id, datasets in sorted(by_provider.items()):
        provider = provider_by_id(provider_id)
        if provider is not None:
            label = f"{provider.country_code} — {provider.country_name}"
        else:
            label = datasets[0].name or str(provider_id)

        worst = max(datasets, key=lambda d: _STATUS_RANK.get(d.status, 2)).status
        fill, text = _STATUS_COLOR.get(worst, ("#E8E8E8", "#333333"))

        n_tables = len(datasets)
        n_final = sum(1 for d in datasets if d.status == "FINAL")
        ds_lines = "<br/>".join(
            f"<small>{_esc(ds.table_name)}: {ds.id}</small>"
            for ds in sorted(datasets, key=lambda d: d.table_name)
        )
        full_label = (
            f"{_esc(label)}<br/>{ds_lines}<br/><small>{n_final}/{n_tables} FINAL</small>"
        )

        nid = f"p_{provider_id}"
        lines.append(f'    {nid}["{full_label}"]')
        lines.append(f"    style {nid} fill:{fill},color:{text},stroke:#999")
        lines.append(f"    df --> {nid}")

    return "\n".join(lines)
