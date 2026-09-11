"""Extract a self-contained subset of the 2022 UWWTD reported data for Toulon (FR) and surrounds.

Seeds on FR agglomerations within RADIUS_KM of Toulon city centre, then closes the
plant<->agglomeration graph so no link in the subset dangles: any plant serving a seed
agglomeration is included, and any *other* agglomeration that plant also serves is pulled
in too (which matters because Alg6 expands plants across agglomerations and
`aggIdBiggestLoad` picks the largest agglomeration a plant serves).

Usage:  python temp/toulon/extract_toulon.py [radius_km]
"""

import math
import sys
from pathlib import Path

import polars as pl

SRC = Path("data/data_uwwtd_import_1043/data_input")
OUT = Path("temp/toulon")

# Toulon city centre (Place de la Liberté)
LAT, LON = 43.1242, 5.9280
RADIUS_KM = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0


def haversine(lat, lon):
    if lat is None or lon is None:
        return float("inf")
    p = math.pi / 180
    a = (
        math.sin((lat - LAT) * p / 2) ** 2
        + math.cos(LAT * p) * math.cos(lat * p) * math.sin((lon - LON) * p / 2) ** 2
    )
    return 2 * 6371 * math.asin(min(1.0, math.sqrt(a)))


def read(name):
    return pl.read_parquet(SRC / f"{name}.parquet")


def main():
    agglo_all = read("Agglomerations")
    uww_all = read("UWWTPs")
    link_all = read("UwwtpAgglos")

    # --- seed: FR agglomerations within the radius -------------------------------
    fr = agglo_all.filter(pl.col("aggCode").str.starts_with("FR"))
    dist = [haversine(la, lo) for la, lo in zip(fr["aggLatitude"], fr["aggLongitude"])]
    fr = fr.with_columns(pl.Series("km_from_toulon", dist))
    seed = set(fr.filter(pl.col("km_from_toulon") <= RADIUS_KM)["aggCode"].to_list())
    print(f"seed agglomerations within {RADIUS_KM:g} km: {len(seed)}")

    # --- close the plant <-> agglomeration graph ---------------------------------
    aggs, plants = set(seed), set()
    while True:
        new_plants = set(
            link_all.filter(pl.col("aucAggCode").is_in(list(aggs)))["aucUwwCode"].to_list()
        ) | set(uww_all.filter(pl.col("aggCode").is_in(list(aggs)))["uwwCode"].to_list())
        new_aggs = set(
            link_all.filter(pl.col("aucUwwCode").is_in(list(plants | new_plants)))[
                "aucAggCode"
            ].to_list()
        ) | set(
            uww_all.filter(pl.col("uwwCode").is_in(list(plants | new_plants)))["aggCode"].to_list()
        )
        new_aggs.discard(None)
        new_plants.discard(None)
        if new_plants <= plants and new_aggs <= aggs:
            break
        plants |= new_plants
        aggs |= new_aggs
    print(f"after closure: {len(aggs)} agglomerations, {len(plants)} plants")
    print(f"  pulled in by closure: {sorted(aggs - seed)}")

    agglos = list(aggs)
    uwws = list(plants)

    # --- discharge points and the receiving areas they name ----------------------
    dcp = read("DischargePoints").filter(pl.col("uwwCode").is_in(uwws))
    rcas = set(dcp["rcaCode"].drop_nulls().to_list())
    sasa_all = read("ReceivingAreasSASA")
    rcas |= set(
        sasa_all.filter(pl.col("rcaCode").is_in(list(rcas)))["rcaRelatedSA"].drop_nulls().to_list()
    )
    rcas = [r for r in rcas if r]
    print(f"discharge points: {dcp.height}, receiving areas: {len(rcas)}")

    fr_snap = read("ReportPeriod").filter(pl.col("rptMStateKey") == "FR")

    tables = {
        "Agglomerations": agglo_all.filter(pl.col("aggCode").is_in(agglos)),
        "UWWTPs": uww_all.filter(pl.col("uwwCode").is_in(uwws)),
        "UwwtpAgglos": link_all.filter(
            pl.col("aucUwwCode").is_in(uwws) | pl.col("aucAggCode").is_in(agglos)
        ),
        "DischargePoints": dcp,
        "ReceivingAreasSAMain": read("ReceivingAreasSAMain").filter(pl.col("rcaCode").is_in(rcas)),
        "ReceivingAreasSAParameter": read("ReceivingAreasSAParameter").filter(
            pl.col("rcaCode").is_in(rcas)
        ),
        "ReceivingAreasSA54": read("ReceivingAreasSA54").filter(pl.col("rcaCode").is_in(rcas)),
        "ReceivingAreasSASA": sasa_all.filter(pl.col("rcaCode").is_in(rcas)),
        "ReceivingAreasLSA": read("ReceivingAreasLSA").filter(pl.col("rcaCode").is_in(rcas)),
        "ReportPeriod": fr_snap,
        # MSLevel carries the country in countryCode; its rptMStateKey column is all-null
        "MSLevel": read("MSLevel").filter(pl.col("countryCode") == "FR"),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.write_parquet(OUT / f"{name}.parquet")
        df.write_csv(OUT / f"{name}.csv")
        print(f"  {name:28s} {df.height:5d} rows")

    # distance reference for the seed, handy for widening/narrowing the radius
    fr.filter(pl.col("aggCode").is_in(agglos)).select(
        ["aggCode", "aggName", "aggNUTS", "aggState", "aggGenerated", "km_from_toulon"]
    ).sort("km_from_toulon").write_csv(OUT / "_agglomerations_by_distance.csv")


if __name__ == "__main__":
    main()
