"""Resolve US "City, ST" names to coordinates using Census Gazetteer records.

The fuel dataset only gives a station's city and state (its addresses are highway
exits, not street addresses), so a city's internal point is the best location we
have for a station. The same index resolves "City, ST" trip endpoints.
"""

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from enum import IntEnum
from typing import NamedTuple


class Point(NamedTuple):
    latitude: float
    longitude: float


class PlaceKind(IntEnum):
    """Gazetteer record kinds, in order of preference when names collide."""

    INCORPORATED = 0
    CDP = 1
    COUNTY_SUBDIVISION = 2


@dataclass(frozen=True)
class PlaceRecord:
    state: str
    name: str
    latitude: float
    longitude: float
    kind: PlaceKind
    land_area: int


# Census appends a lowercase legal description ("Tomah city", "Mahwah township").
# Case matters: "Carson City" is the place's actual name, not a suffix.
_LEGAL_SUFFIX = re.compile(
    r"\s+(city and borough|city|town|township|village|CDP|borough|municipality"
    r"|plantation|comunidad|zona urbana|corporation)$"
)
_GOVERNMENT_SUFFIX = re.compile(
    r"\s+(metropolitan government|metro government|consolidated government"
    r"|unified government|urban county)\b.*$"
)
_BALANCE_SUFFIX = re.compile(r"\s*\(balance\)$")
_GOVERNMENT_PREFIX = re.compile(r"^(Town|City|Village) of\s+")
_TRAILING_CITY = re.compile(r"\s+City$")

_WORD_ABBREVIATIONS = {"saint": "st", "sainte": "ste", "fort": "ft", "mount": "mt"}

US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH"
    " NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)

# Gazetteer LSAD code for a census-designated (unincorporated) place.
_CDP_LSAD = "57"

# County subdivisions that are real municipalities (New England towns, townships).
# Statistical divisions (CCDs, districts, precincts) can span a whole county.
_MUNICIPAL_SUBDIVISION = re.compile(r"\s(town|township|borough|city|village|plantation)$")


def normalize_place_name(name: str) -> str:
    """Fold spelling variants so "St. Cloud" and "Saint Cloud" compare equal."""
    words = name.lower().replace(".", " ").split()
    folded = "".join(_WORD_ABBREVIATIONS.get(word, word) for word in words)
    return re.sub(r"[^a-z]", "", folded)


def place_name_variants(gazetteer_name: str) -> list[tuple[str, bool]]:
    """Return (name, is_alias) pairs a Gazetteer record should be found under.

    The first entry is the official name without Census descriptors; the rest are
    looser aliases ("Boise City" -> "Boise") used only when nothing matches exactly.
    """
    name = _BALANCE_SUFFIX.sub("", gazetteer_name)
    name = _GOVERNMENT_SUFFIX.sub("", name)
    name = _LEGAL_SUFFIX.sub("", name)

    aliases = [
        re.split(r"[-/]", name)[0],
        _GOVERNMENT_PREFIX.sub("", name),
        _TRAILING_CITY.sub("", name),
    ]
    variants = [(name, False)]
    for alias in aliases:
        if all(alias != existing for existing, _ in variants):
            variants.append((alias, True))
    return variants


def place_record_from_gazetteer(row: dict, source: str) -> PlaceRecord | None:
    """Convert a Gazetteer "place" or "county_subdivision" row, or None to skip it."""
    if row["USPS"] not in US_STATE_CODES:
        return None
    if source == "place":
        kind = PlaceKind.CDP if row["LSAD"] == _CDP_LSAD else PlaceKind.INCORPORATED
    elif _MUNICIPAL_SUBDIVISION.search(row["NAME"]):
        kind = PlaceKind.COUNTY_SUBDIVISION
    else:
        return None
    return PlaceRecord(
        state=row["USPS"],
        name=row["NAME"],
        latitude=float(row["INTPTLAT"]),
        longitude=float(row["INTPTLONG"]),
        kind=kind,
        land_area=int(row["ALAND"]),
    )


PLACE_CSV_FIELDS = ("state", "name", "kind", "land_area", "latitude", "longitude")


def load_place_records(path):
    """Read the trimmed place file produced by scripts/build_us_places.py."""
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            yield PlaceRecord(
                state=row["state"],
                name=row["name"],
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                kind=PlaceKind[row["kind"]],
                land_area=int(row["land_area"]),
            )


class PlaceIndex:
    def __init__(self, records):
        self._candidates = defaultdict(list)
        for record in records:
            for name, is_alias in place_name_variants(record.name):
                key = (record.state, normalize_place_name(name))
                self._candidates[key].append((is_alias, record))

    def resolve(self, city: str, state: str) -> PlaceRecord | None:
        key = (state.strip().upper(), normalize_place_name(city))
        candidates = self._candidates.get(key)
        if not candidates:
            return None
        _, best = min(
            candidates,
            key=lambda candidate: (candidate[0], candidate[1].kind, -candidate[1].land_area),
        )
        return best
