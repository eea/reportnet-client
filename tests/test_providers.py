from reportnet.providers import PROVIDERS, by_group


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
