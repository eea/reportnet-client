from __future__ import annotations

from typing import Literal, NamedTuple


class DataProvider(NamedTuple):
    provider_id: int
    country_code: str
    country_name: str
    eea_group: str
    eurostat_group: str


PROVIDERS: tuple[DataProvider, ...] = (
    DataProvider(42, "AD", "Andorra",                   "Other",                    "Other"),
    DataProvider(41, "AL", "Albania",                   "EEA Cooperating country",  "EU Candidate country"),
    DataProvider(43, "AM", "Armenia",                   "ENP East",                 "ENP East"),
    DataProvider( 2, "AT", "Austria",                   "EEA",                      "EU"),
    DataProvider(44, "AT", "Austria",                   "EEA",                      "EU"),
    DataProvider(45, "AZ", "Azerbaijan",                "ENP East",                 "ENP East"),
    DataProvider(48, "BA", "Bosnia and Herzegovina",    "EEA Cooperating country",  "EU Candidate country"),
    DataProvider( 6, "BE", "Belgium",                   "EEA",                      "EU"),
    DataProvider(47, "BE", "Belgium",                   "EEA",                      "EU"),
    DataProvider( 7, "BG", "Bulgaria",                  "EEA",                      "EU"),
    DataProvider(49, "BG", "Bulgaria",                  "EEA",                      "EU"),
    DataProvider(46, "BY", "Belarus",                   "ENP East",                 "ENP East"),
    DataProvider(11, "CH", "Switzerland",               "EEA",                      "EFTA"),
    DataProvider(88, "CH", "Switzerland",               "EEA",                      "EFTA"),
    DataProvider(15, "CY", "Cyprus",                    "EEA",                      "EU"),
    DataProvider(51, "CY", "Cyprus",                    "EEA",                      "EU"),
    DataProvider(18, "CZ", "Czechia",                   "EEA",                      "EU"),
    DataProvider(52, "CZ", "Czechia",                   "EEA",                      "EU"),
    DataProvider(27, "DE", "Germany",                   "EEA",                      "EU"),
    DataProvider(58, "DE", "Germany",                   "EEA",                      "EU"),
    DataProvider(22, "DK", "Denmark",                   "EEA",                      "EU"),
    DataProvider(53, "DK", "Denmark",                   "EEA",                      "EU"),
    DataProvider(24, "EE", "Estonia",                   "EEA",                      "EU"),
    DataProvider(54, "EE", "Estonia",                   "EEA",                      "EU"),
    DataProvider( 1, "EL", "Greece",                    "EEA",                      "EU"),
    DataProvider(60, "EL", "Greece",                    "EEA",                      "EU"),
    DataProvider(33, "ES", "Spain",                     "EEA",                      "EU"),
    DataProvider(86, "ES", "Spain",                     "EEA",                      "EU"),
    DataProvider(25, "FI", "Finland",                   "EEA",                      "EU"),
    DataProvider(55, "FI", "Finland",                   "EEA",                      "EU"),
    DataProvider(26, "FR", "France",                    "EEA",                      "EU"),
    DataProvider(56, "FR", "France",                    "EEA",                      "EU"),
    DataProvider(57, "GE", "Georgia",                   "ENP East",                 "EU Potential candidate"),
    DataProvider(59, "GI", "Gibraltar",                 "Other",                    "Other"),
    DataProvider(12, "HR", "Croatia",                   "EEA",                      "EU"),
    DataProvider(50, "HR", "Croatia",                   "EEA",                      "EU"),
    DataProvider(14, "HU", "Hungary",                   "EEA",                      "EU"),
    DataProvider(61, "HU", "Hungary",                   "EEA",                      "EU"),
    DataProvider(17, "IE", "Ireland",                   "EEA",                      "EU"),
    DataProvider(63, "IE", "Ireland",                   "EEA",                      "EU"),
    DataProvider(16, "IS", "Iceland",                   "EEA",                      "EFTA"),
    DataProvider(62, "IS", "Iceland",                   "EEA",                      "EFTA"),
    DataProvider(19, "IT", "Italy",                     "EEA",                      "EU"),
    DataProvider(64, "IT", "Italy",                     "EEA",                      "EU"),
    DataProvider(67, "KG", "Kyrgyzstan",                "Other",                    "Other"),
    DataProvider(65, "KZ", "Kazakhstan",                "Other",                    "Other"),
    DataProvider(21, "LI", "Liechtenstein",             "EEA",                      "EFTA"),
    DataProvider(69, "LI", "Liechtenstein",             "EEA",                      "EFTA"),
    DataProvider(23, "LT", "Lithuania",                 "EEA",                      "EU"),
    DataProvider(70, "LT", "Lithuania",                 "EEA",                      "EU"),
    DataProvider(28, "LU", "Luxembourg",                "EEA",                      "EU"),
    DataProvider(71, "LU", "Luxembourg",                "EEA",                      "EU"),
    DataProvider(20, "LV", "Latvia",                    "EEA",                      "EU"),
    DataProvider(68, "LV", "Latvia",                    "EEA",                      "EU"),
    DataProvider(74, "MC", "Monaco",                    "Other",                    "Other"),
    DataProvider(73, "MD", "Moldova",                   "ENP East",                 "EU Candidate country"),
    DataProvider(75, "ME", "Montenegro",                "EEA Cooperating country",  "EU Candidate country"),
    DataProvider(77, "MK", "North Macedonia",           "EEA Cooperating country",  "EU Candidate country"),
    DataProvider(29, "MT", "Malta",                     "EEA",                      "EU"),
    DataProvider(72, "MT", "Malta",                     "EEA",                      "EU"),
    DataProvider( 8, "NL", "Netherlands",               "EEA",                      "EU"),
    DataProvider(76, "NL", "Netherlands",               "EEA",                      "EU"),
    DataProvider(40, "NO", "Norway",                    "EEA",                      "EFTA"),
    DataProvider(78, "NO", "Norway",                    "EEA",                      "EFTA"),
    DataProvider( 9, "PL", "Poland",                    "EEA",                      "EU"),
    DataProvider(79, "PL", "Poland",                    "EEA",                      "EU"),
    DataProvider(13, "PT", "Portugal",                  "EEA",                      "EU"),
    DataProvider(80, "PT", "Portugal",                  "EEA",                      "EU"),
    DataProvider( 5, "RO", "Romania",                   "EEA",                      "EU"),
    DataProvider(81, "RO", "Romania",                   "EEA",                      "EU"),
    DataProvider(83, "RS", "Serbia",                    "EEA Cooperating country",  "EU Candidate country"),
    DataProvider(82, "RU", "Russia",                    "Other",                    "Other"),
    DataProvider(10, "SE", "Sweden",                    "EEA",                      "EU"),
    DataProvider(87, "SE", "Sweden",                    "EEA",                      "EU"),
    DataProvider(32, "SI", "Slovenia",                  "EEA",                      "EU"),
    DataProvider(85, "SI", "Slovenia",                  "EEA",                      "EU"),
    DataProvider(31, "SK", "Slovakia",                  "EEA",                      "EU"),
    DataProvider(84, "SK", "Slovakia",                  "EEA",                      "EU"),
    DataProvider(89, "TJ", "Tajikistan",                "Other",                    "Other"),
    DataProvider(91, "TM", "Turkmenistan",              "Other",                    "Other"),
    DataProvider(34, "TR", "Turkey",                    "EEA",                      "EU Candidate country"),
    DataProvider(90, "TR", "Turkey",                    "EEA",                      "EU Candidate country"),
    DataProvider(92, "UA", "Ukraine",                   "ENP East",                 "EU Candidate country"),
    DataProvider(93, "UK", "United Kingdom",            "Other",                    "Other"),
    DataProvider(94, "UZ", "Uzbekistan",                "Other",                    "Other"),
    DataProvider(66, "XK", "Kosovo",                    "EEA Cooperating country",  "EU Potential candidate"),
)

_BY_ID: dict[int, DataProvider] = {p.provider_id: p for p in PROVIDERS}

_BY_COUNTRY: dict[str, list[DataProvider]] = {}
for _p in PROVIDERS:
    _BY_COUNTRY.setdefault(_p.country_code, []).append(_p)


def by_id(provider_id: int) -> DataProvider | None:
    """Return the DataProvider for a given provider ID, or None if not found."""
    return _BY_ID.get(provider_id)


def by_country(country_code: str) -> list[DataProvider]:
    """Return all DataProviders for a given ISO country code (e.g. 'AT', 'IE')."""
    return _BY_COUNTRY.get(country_code.upper(), [])


GroupField = Literal["eea_group", "eurostat_group"]


def by_group(
    group: str,
    *,
    field: GroupField = "eea_group",
) -> list[DataProvider]:
    """Return all DataProviders belonging to a named group.

    group: e.g. 'EEA', 'EU', 'EFTA', 'ENP East', 'EEA Cooperating country', 'Other'.
    field: 'eea_group' (default) or 'eurostat_group'.
    """
    return [p for p in PROVIDERS if getattr(p, field) == group]
