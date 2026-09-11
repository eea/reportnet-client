# Toulon subset — UWWTD Art. 15, reference year 2022

A self-contained extract of the French 2022 reported data covering Toulon and its
surrounding towns. Every table is filtered to the same set of agglomerations and plants,
with no dangling references.

**Source:** `data/data_uwwtd_import_1043/data_input/` (dataset 1043, FR envelope `FR2022`,
`repVersion` 2023-12-05, `repReportedPeriod` 2022)
**Extracted:** 2026-09-09 · **Radius:** 25 km

## Selection rule

Seeded on FR agglomerations whose reported coordinates lie within 25 km of Toulon city
centre (43.1242 N, 5.9280 E), then closed over the plant ↔ agglomeration graph: any plant
serving a seed agglomeration is pulled in, and any *other* agglomeration such a plant also
serves is pulled in too. Closure added nothing here — the 15 agglomerations map 1:1 onto
15 plants — but the step matters in general, because Algorithm 6 expands plants across
agglomerations and `aggIdBiggestLoad` picks the largest agglomeration a plant serves.

Geography, not name matching. `FR040000171542 TOULON-SUR-ARROUX` (732 p.e., Saône-et-Loire)
shares the name but sits ~500 km north, and is **not** included.

To regenerate at a different radius:

```bash
python temp/toulon/extract_toulon.py 40
```

That run also writes `_agglomerations_by_distance.csv`, listing each included agglomeration
with its distance from Toulon, so you can see what a wider or narrower radius would add or
drop. It is a scratch aid, not part of this fixture, and is not kept here.

## Contents

Reported source tables, named and shaped exactly as in `data_input/`:

| File | Rows |
|---|---|
| `Agglomerations` | 15 |
| `UWWTPs` | 15 |
| `UwwtpAgglos` | 15 |
| `DischargePoints` | 15 |
| `ReceivingAreasSAMain` | 2 |
| `ReceivingAreasSAParameter` | 2 |
| `ReceivingAreasSA54` | 2 |
| `ReceivingAreasSASA` | 1 |
| `ReceivingAreasLSA` | 0 |
| `ReportPeriod` | 1 |
| `MSLevel` | 1 |

Each is written as both `.parquet` (types preserved, what the pipeline loads) and `.csv`
(for inspection). No derived or computed output is kept here — these are reported source
tables only.

`ProtectedArea` is not among them: it is not an input to `run_compliance()`. It does,
however, have a key into this subset — `rcaCode` matches its `thematicIdIdentifier`,
which is what the dataflow's `Cross01` check joins on — so the matching geometries live
alongside in [`spatial/`](spatial/README.md), as a GeoPackage covering the same 25 km.

## The agglomerations

| aggCode | Name | p.e. | km |
|---|---|---|---|
| FR060000183137 | TOULON/LA SEYNE-SUR-MER | 305 512 | 1.8 |
| FR060000283137 | GARDE/TOULON | 64 193 | 7.9 |
| FR060000183123 | SANARY-SUR-MER | 45 698 | 10.6 |
| FR060000183016 | BEAUSSET-INTERCOMMUNALE | 18 968 | 12.8 |
| FR060000183047 | CRAU | 44 569 | 12.9 |
| FR060000183069 | HYERES/LES PALMIERS | 59 111 | 17.3 |
| FR060000283069 | HYERES/PORQUEROLLES | 2 813 | 17.3 |
| FR060000183049 | CUERS | 9 278 | 17.6 |
| FR060000183112 | SAINT-CYR-SUR-MER | 17 192 | 18.6 |
| FR060000183127 | SIGNES | 1 683 | 18.8 |
| FR060000183091 | PIERREFEU-DU-VAR | 4 648 | 23.8 |
| FR060000183100 | PUGET-VILLE | 3 675 | 24.2 |
| FR060000183106 | ROCBARON/FORCALQUEIRET | 7 175 | 24.3 |
| FR060000183108 | ROQUEBRUSSANNE | 2 271 | 24.7 |
| FR060000113030 | CUGES-LES-PINS | 3 524 | 25.0 |

All are active (`aggState = 1`). Thirteen are in Var (NUTS FRL05); CUGES-LES-PINS is in
Bouches-du-Rhône (FRL04). Total generated load: 590 300 p.e.

## Verified self-contained

Running `run_compliance()` on this subset alone gives results **identical** to running it
on the full 26 064-plant / 25 208-agglomeration 2022 dataset and filtering down to these
rows — checked on `result_required` and `result_compliance` for plants, and on every
`result_*` column for agglomerations.

```python
import sys; sys.path.insert(0, "tests")
from pathlib import Path
from test_helpers import load_dfs
from compliance.run_algorithm import run_compliance

d = load_dfs(Path("temp/toulon"))
plants, agglos, dtt = run_compliance(
    uwwtps=d["uwwtps"], discharge_points=d["discharge_points"],
    receiving_areas_sa_main=d["receiving_areas_sa_main"],
    receiving_areas_sa_parameter=d["receiving_areas_sa_parameter"],
    receiving_areas_sa54=d["receiving_areas_sa54"],
    uwwtp_agglos=d["uwwtp_agglos"], agglomerations=d["agglomerations"],
    report_period=d["report_period"],
)
```

`load_dfs()` injects the `uwwUWWTPSID` / `aggAgglomorationsID` / `ReceivingAreas_SAMainId`
UUIDs, which are absent from the raw parquets.

## What the data says

Two receiving areas, both the Gapeau catchment (`FRSA_CM_06318` coastal, `FRSA_RI_06318`
river), designated sensitive for **phosphorus only** (`rcaParameterP = true`,
`rcaParameterN = false`), `rcaStartDate` 2017-06-04. Five inland plants discharge into it
under `dcpTypeOfReceivingArea = A54`; the coastal plants — Cap Sicié, Almanarre, La Cride,
Pointe Grenier, Pont de la Clue — discharge to `NA` coastal water.

No agglomeration in the subset has an Article 5 deadline (`aggDateArt5` is null throughout),
so Art. 5 is `NR` across the board. Article 3 and 4 deadlines are all 2000-12-31 or
2005-12-31 — long past.

Compliance outcome: 12 of 15 agglomerations compliant. Two are non-compliant —
CUGES-LES-PINS (3 524 p.e.) and ROQUEBRUSSANNE (2 271 p.e.), both driven by their plant
failing secondary-treatment performance (`result_compliance = NC`, Art. 4). SIGNES
(1 683 p.e.) is below the 2 000 p.e. threshold and scores `NR` throughout.

Cap Sicié — Amphitria carries 305 512 p.e., over half the subset's load, and is compliant.

## Known defect carried through

The FR 2022 `ReportPeriod` row has `repSituationAt = 2023-12-05` — `repVersion` copied into
the wrong field; it should be `2022-12-31`. This is reproduced verbatim from the source, not
corrected. It has **no effect on this subset**: re-running with the date corrected gives
identical plant and agglomeration results, because every relevant date here (the 2017
`rcaStartDate`, the 2000/2005 Article 3 and 4 deadlines) falls well before both values.
