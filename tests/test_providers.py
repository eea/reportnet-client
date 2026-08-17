from reportnet.providers import PROVIDERS, by_country, by_group, by_id


def test_by_group_eea_returns_only_eea():
    results = by_group("EEA")
    assert len(results) > 0
    assert all(p.eea_group == "EEA" for p in results)


def test_by_group_eurostat_field():
    results = by_group("EU", field="eurostat_group")
    assert len(results) > 0
    assert all(p.eurostat_group == "EU" for p in results)


def test_by_group_returns_empty_for_unknown():
    assert by_group("NONEXISTENT") == []


def test_by_group_other():
    results = by_group("Other")
    assert len(results) > 0
    assert all(p.eea_group == "Other" for p in results)


def test_by_group_covers_all_providers():
    all_groups = {p.eea_group for p in PROVIDERS}
    recovered = []
    for g in all_groups:
        recovered.extend(by_group(g))
    assert set(p.provider_id for p in recovered) == set(p.provider_id for p in PROVIDERS)


# ── documentation examples ────────────────────────────────────────────────────
# Docstrings and docs/ use `for_provider(17)` as the worked "Ireland" example.
# Provider 42 is Andorra — it was previously mislabelled as Ireland throughout.

def test_ireland_example_provider_id_is_actually_ireland():
    ie = by_id(17)
    assert ie is not None
    assert ie.country_code == "IE"
    assert ie.country_name == "Ireland"


def test_provider_42_is_andorra_not_ireland():
    ad = by_id(42)
    assert ad is not None
    assert ad.country_code == "AD"


def test_by_country_finds_both_ireland_provider_ids():
    assert {p.provider_id for p in by_country("IE")} == {17, 63}
