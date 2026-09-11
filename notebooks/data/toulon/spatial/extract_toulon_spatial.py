"""Extract the Toulon spatial subset (UWWTD Art. 15 ProtectedArea) from a national GeoPackage.

Companion to ``../extract_toulon.py``: same centre and radius, so the spatial
and descriptive subsets describe the same place. Selects every protected area
whose geometry comes within RADIUS_KM of Toulon, from both layers — sensitive
areas are split by geometry type, coastal/catchment as MultiPolygon in
``ProtectedArea`` and rivers as MultiLineString in ``ProtectedAreaLine``, so
taking only one layer silently drops half the receiving areas.

Distances are measured in EPSG:3035, the equal-area CRS the dataflow's own
spatial QC uses (``ST_Transform(..., 3035)``), not in degrees.

Usage:  python extract_toulon_spatial.py [path/to/France.gpkg] [radius_km]
"""

import sys
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

HERE = Path(__file__).resolve().parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[1] / "France.gpkg"
RADIUS_KM = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
OUT = HERE / "toulon_protected_areas.gpkg"

# Toulon city centre (Place de la Liberté) — same seed as extract_toulon.py
LAT, LON = 43.1242, 5.9280
LAYERS = ("ProtectedArea", "ProtectedAreaLine")


def main() -> None:
    buffer = (
        gpd.GeoSeries([Point(LON, LAT)], crs="EPSG:4326")
        .to_crs(3035)
        .buffer(RADIUS_KM * 1000)
        .iloc[0]
    )
    print(f"source: {SRC}\nradius: {RADIUS_KM:g} km around {LAT}, {LON}")

    # Remove the whole file first: GPKG mode="w" replaces only the layer it
    # writes, so a stale second layer would survive and mode="a" would append
    # to it — re-running would silently duplicate features.
    OUT.unlink(missing_ok=True)

    selected: dict[str, set[str]] = {}
    for layer in LAYERS:
        gdf = gpd.read_file(SRC, layer=layer)
        hit = gdf[gdf.to_crs(3035).intersects(buffer)].copy().reset_index(drop=True)
        hit.to_file(OUT, layer=layer, driver="GPKG", mode="a")
        selected[layer] = set(hit["thematicIdIdentifier"])
        print(f"  {layer:20s} {len(hit):3d} of {len(gdf)}: {sorted(selected[layer])}")

    # Closure check: predecessors, successors and related zones are validated
    # against the register by the spatial QC (XC01J, RR15B, RW05A, RR19), so a
    # subset that references something it does not contain is not self-contained.
    chosen = set().union(*selected.values())
    dangling: set[str] = set()
    for layer in LAYERS:
        df = gpd.read_file(OUT, layer=layer, ignore_geometry=True)
        for column in (
            "predecessorsIdentifier",
            "successorsIdentifier",
            "relatedZoneIdentifier",
        ):
            for value in df[column].dropna():
                dangling |= {v.strip() for v in str(value).split(",") if v.strip()}
    dangling -= chosen
    print(f"\ndangling references: {sorted(dangling) or 'none'}")
    print(f"written: {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
