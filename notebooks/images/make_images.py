"""Regenerate the illustrations used by ../01_reporter_workflow.py.

Two figures, from the committed Toulon fixture and a saved validation response:

- ``toulon_subset_map.png`` — what the subset *is*: agglomerations, the plants
  serving them, and the sensitive area they discharge into.
- ``validation_results.png`` — what came back from validating it.

Colours come from a validated categorical palette. Severity is deliberately the
*axis category* rather than a colour encoding: the natural red/amber status pair
sits below the normal-vision separation floor, so using it to carry identity
would make two bars hard to tell apart for everyone, not just colour-blind
readers. One hue plus a labelled axis avoids that entirely.

Usage:  python make_images.py
"""

import json
import math
from pathlib import Path

import geopandas as gpd
import matplotlib
import polars as pl

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "toulon"

SURFACE, INK, INK2, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#ececea", "#d8d8d4"
AGG, PLANT, AREA = "#2a78d6", "#eb6834", "#1baf7a"  # categorical slots 1, 2, 3

TOULON_LAT, TOULON_LON = 43.1242, 5.9280


def _frame(ax: "plt.Axes") -> None:
    ax.tick_params(labelsize=7.5, colors=INK2)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)


def _marker_size(values, vmax: float, lo: float = 14, hi: float = 300) -> list[float]:
    """Area proportional to sqrt(value) — keeps one huge plant from swamping the rest."""
    return [lo + (hi - lo) * math.sqrt(max(v, 0) / vmax) for v in values]


def map_figure() -> None:
    ag = pl.read_parquet(DATA / "Agglomerations.parquet")
    uw = pl.read_parquet(DATA / "UWWTPs.parquet")
    gpkg = DATA / "spatial" / "toulon_protected_areas.gpkg"

    fig, ax = plt.subplots(figsize=(9.5, 6.0), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    if gpkg.exists():
        gpd.read_file(gpkg, layer="ProtectedArea").plot(
            ax=ax, facecolor=AREA, edgecolor=AREA, alpha=0.12, linewidth=1.1, zorder=1
        )
        gpd.read_file(gpkg, layer="ProtectedAreaLine").plot(
            ax=ax, color=AREA, linewidth=1.5, alpha=0.8, zorder=2
        )

    ax.scatter(
        ag["aggLongitude"], ag["aggLatitude"],
        s=_marker_size(ag["aggGenerated"], 305512),
        facecolor=AGG, edgecolor=SURFACE, linewidth=1.3, alpha=0.85, zorder=3,
        label="Agglomeration — size = p.e. generated",
    )
    ax.scatter(
        uw["uwwLongitude"], uw["uwwLatitude"],
        s=_marker_size(uw["uwwCapacity"], 500000), marker="s",
        facecolor=PLANT, edgecolor=SURFACE, linewidth=1.3, alpha=0.9, zorder=4,
        label="Treatment plant — size = design capacity",
    )

    ax.plot(TOULON_LON, TOULON_LAT, marker="*", ms=14, color=INK, zorder=6)
    ax.annotate("TOULON", (TOULON_LON, TOULON_LAT), xytext=(0, -17),
                textcoords="offset points", fontsize=8.5, color=INK,
                weight="bold", ha="center", zorder=6)
    ax.annotate("Cap Sicié — Amphitria\n305 512 p.e., compliant", (5.8563, 43.0480),
                xytext=(12, -4), textcoords="offset points", fontsize=7.5,
                color=INK2, zorder=6)
    ax.annotate("Gapeau catchment\n(sensitive area)", (6.20, 43.30), fontsize=7.5,
                color="#12805a", ha="center", zorder=6)

    # degrees of longitude are shorter than degrees of latitude at 43°N
    ax.set_aspect(1 / math.cos(math.radians(TOULON_LAT)))
    ax.set_title("The Toulon subset — 15 agglomerations, 15 plants, 2 sensitive areas",
                 fontsize=11.5, color=INK, pad=10, loc="left")
    ax.set_xlabel("Longitude", fontsize=8, color=INK2)
    ax.set_ylabel("Latitude", fontsize=8, color=INK2)
    _frame(ax)
    ax.grid(True, color=GRID, linewidth=0.6, zorder=0)
    legend = ax.legend(loc="lower left", fontsize=8, frameon=True, facecolor=SURFACE,
                       edgecolor=AXIS, labelcolor=INK2, scatterpoints=1)
    for handle in legend.legend_handles:
        handle.set_sizes([40])
    fig.tight_layout()
    fig.savefig(HERE / "toulon_subset_map.png", facecolor=SURFACE)
    print("wrote toulon_subset_map.png")


def results_figure() -> None:
    rows = json.loads((HERE / "validation_results.json").read_text())["errors"]
    severity = {"BLOCKER": 0, "ERROR": 1, "WARNING": 2}
    rows.sort(key=lambda e: (severity[e["levelError"]], -int(e["numberOfRecords"])))
    labels = [f"{e['levelError']}   {e['nameTableSchema']} · {e['shortCode']}" for e in rows]
    values = [int(e["numberOfRecords"]) for e in rows]

    fig, ax = plt.subplots(figsize=(9.5, 4.6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    y = list(range(len(rows)))
    ax.barh(y, values, color=AGG, height=0.62, zorder=3)
    for i, v in zip(y, values):
        ax.text(v + 0.35, i, str(v), va="center", fontsize=8.5, color=INK2, zorder=4)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8, color=INK2)
    ax.invert_yaxis()
    ax.set_xlabel("records flagged", fontsize=8, color=INK2)
    ax.set_xlim(0, max(values) * 1.12)
    _frame(ax)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(True, axis="x", color=GRID, linewidth=0.6, zorder=0)
    fig.suptitle(
        f"Validation of the Toulon upload — {len(rows)} rules fired, "
        f"{sum(values)} records flagged",
        fontsize=11.5, color=INK, x=0.012, ha="left", y=0.975,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(HERE / "validation_results.png", facecolor=SURFACE)
    print("wrote validation_results.png")


if __name__ == "__main__":
    map_figure()
    results_figure()
