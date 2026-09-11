# Toulon spatial subset — UWWTD Art. 15 ProtectedArea

The spatial half of the [Toulon subset](../README.md): every protected area whose
geometry comes within 25 km of Toulon, extracted from a national `France.gpkg`.
Same centre and radius as the descriptive extract, so the two describe the same place.

**Source:** `notebooks/data/France.gpkg` (172 `ProtectedArea` + 139 `ProtectedAreaLine`
features, EPSG:4326, 60 MB)
**Extracted:** 2026-09-11 · **Radius:** 25 km · **Centre:** 43.1242 N, 5.9280 E

## Contents

`toulon_protected_areas.gpkg` (228 KB), two layers, EPSG:4326 preserved:

| Layer | Geometry | Features | |
|---|---|---|---|
| `ProtectedArea` | MultiPolygon | 3 | `FRSA_CM_06318`, `FRSA_CM_06326`, `FRSA_CM_06340` |
| `ProtectedAreaLine` | MultiLineString | 2 | `FRSA_RI_06318`, `FRSA_RI_06340` |

All five carry the 27 fields of the dataflow's `ProtectedArea` schema, all geometries
are valid, and `wiseEvolutionType` is `noChange` throughout.

**Sensitive areas are split across the two layers by geometry type** — coastal and
catchment areas are polygons, rivers are lines. Reading only `ProtectedArea` silently
drops half the receiving areas, including `FRSA_RI_06318`.

## Why these five

The descriptive subset reports two receiving areas, and they are one from each layer:

- `FRSA_CM_06318` — BASSIN VERSANT DU GAPEAU, catchment (polygon)
- `FRSA_RI_06318` — BASSIN VERSANT DU GAPEAU, river (line)

Both are present, so the cross-dataset check `Cross01`
(`ReceivingAreasSAMain.rcaCode = ProtectedArea.thematicIdIdentifier`) resolves, as does
`DischargePoints.rcaCode`. The other three (Huveaune, Eygoutier) fall inside the radius
and are kept as neighbouring context.

## Self-contained

No dangling references: nothing in `predecessorsIdentifier`, `successorsIdentifier` or
`relatedZoneIdentifier` points outside the five. That matters because the spatial QC
(`XC01J`, `RR15B`, `RW05A`, `RR19`) validates those against the register, and a subset
that references what it does not contain would fail for the wrong reason.

## Regenerating

```bash
python extract_toulon_spatial.py [path/to/France.gpkg] [radius_km]
```

Distances are measured in EPSG:3035 — the equal-area CRS the dataflow's own spatial QC
uses via `ST_Transform(..., 3035)` — not in degrees. The script deletes the output first
and is safe to re-run: GPKG `mode="w"` replaces only the layer being written, so without
that a stale layer survives and the next append duplicates it.

## Why GeoPackage and not GeoParquet

GeoPackage holds both geometry types in one file with the CRS intact, and reads through
the `pyogrio` that `geopandas` already uses — `pip install reportnet-client[spatial]`.
GeoParquet would need `pyarrow`, which is not a dependency of this project in any extra
(`spatial` is just `geopandas`; `dataframe` is `narwhals` + `polars`, and polars reads
plain parquet without it). It is also the format Reportnet itself exports spatial data
as (integration 11004). Splitting into one GeoParquet per layer would trade a dependency
for no gain at this size.
