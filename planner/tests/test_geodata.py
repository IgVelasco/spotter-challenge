import pytest

from planner.geodata import (
    PlaceIndex,
    PlaceKind,
    PlaceRecord,
    load_place_records,
    normalize_place_name,
    place_name_variants,
    place_record_from_gazetteer,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Big Cabin", "bigcabin"),
        ("  Tomah ", "tomah"),
        ("Saint Cloud", "stcloud"),
        ("St. Cloud", "stcloud"),
        ("Mc Calla", "mccalla"),
        ("De Forest", "deforest"),
        ("Fort Worth", "ftworth"),
        ("Mount Vernon", "mtvernon"),
    ],
)
def test_normalize_place_name_folds_spelling_variants(raw, expected):
    assert normalize_place_name(raw) == expected


@pytest.mark.parametrize(
    ("gazetteer_name", "expected"),
    [
        ("Abbeville city", [("Abbeville", False)]),
        ("Abanda CDP", [("Abanda", False)]),
        ("Oklahoma City city", [("Oklahoma City", False), ("Oklahoma", True)]),
        ("Boise City city", [("Boise City", False), ("Boise", True)]),
        ("Town of Pecos city", [("Town of Pecos", False), ("Pecos", True)]),
        (
            "Nashville-Davidson metropolitan government (balance)",
            [("Nashville-Davidson", False), ("Nashville", True)],
        ),
        (
            "Louisville/Jefferson County metro government (balance)",
            [("Louisville/Jefferson County", False), ("Louisville", True)],
        ),
        ("Mahwah township", [("Mahwah", False)]),
        ("Carson City", [("Carson City", False), ("Carson", True)]),
    ],
)
def test_place_name_variants_strip_census_suffixes(gazetteer_name, expected):
    assert place_name_variants(gazetteer_name) == expected


def _place(name, state="WI", lat=1.0, lon=2.0, kind=PlaceKind.INCORPORATED, land_area=100):
    return PlaceRecord(
        state=state,
        name=name,
        latitude=lat,
        longitude=lon,
        kind=kind,
        land_area=land_area,
    )


def test_index_resolves_city_and_state():
    index = PlaceIndex([_place("Tomah city", lat=43.98, lon=-90.5)])

    assert index.resolve("Tomah", "WI").latitude == 43.98
    assert index.resolve("tomah ", "wi").longitude == -90.5


def test_index_returns_none_for_unknown_place_or_wrong_state():
    index = PlaceIndex([_place("Tomah city")])

    assert index.resolve("Nowhere", "WI") is None
    assert index.resolve("Tomah", "MN") is None


def test_exact_name_wins_over_alias():
    index = PlaceIndex(
        [_place("Lake City city", state="FL", lat=1.0), _place("Lake city", state="FL", lat=2.0)]
    )

    assert index.resolve("Lake", "FL").latitude == 2.0
    assert index.resolve("Lake City", "FL").latitude == 1.0


def test_alias_resolves_when_no_exact_match():
    index = PlaceIndex([_place("Boise City city", state="ID", lat=43.6)])

    assert index.resolve("Boise", "ID").latitude == 43.6


def test_incorporated_place_wins_over_census_designated_place():
    index = PlaceIndex(
        [
            _place("Marion CDP", state="IN", lat=1.0, kind=PlaceKind.CDP, land_area=999),
            _place("Marion city", state="IN", lat=2.0, land_area=10),
        ]
    )

    assert index.resolve("Marion", "IN").latitude == 2.0


def test_larger_place_wins_between_equally_ranked_candidates():
    index = PlaceIndex(
        [
            _place("Superior village", lat=1.0, land_area=3),
            _place("Superior city", lat=2.0, land_area=94),
        ]
    )

    assert index.resolve("Superior", "WI").latitude == 2.0


def test_census_place_wins_over_county_subdivision():
    index = PlaceIndex(
        [
            _place("Edison township", state="NJ", lat=1.0, kind=PlaceKind.COUNTY_SUBDIVISION),
            _place("Edison CDP", state="NJ", lat=2.0, kind=PlaceKind.CDP),
        ]
    )

    assert index.resolve("Edison", "NJ").latitude == 2.0


def _gazetteer_row(name, state="NJ", lsad=None):
    row = {
        "USPS": state,
        "NAME": name,
        "ALAND": "1000",
        "INTPTLAT": "40.5",
        "INTPTLONG": "-74.4",
    }
    if lsad is not None:
        row["LSAD"] = lsad
    return row


def test_place_row_becomes_incorporated_record():
    record = place_record_from_gazetteer(_gazetteer_row("Edison city", lsad="25"), "place")

    assert record == PlaceRecord(
        state="NJ",
        name="Edison city",
        latitude=40.5,
        longitude=-74.4,
        kind=PlaceKind.INCORPORATED,
        land_area=1000,
    )


def test_place_row_with_cdp_code_becomes_cdp_record():
    record = place_record_from_gazetteer(_gazetteer_row("Edison CDP", lsad="57"), "place")

    assert record.kind == PlaceKind.CDP


@pytest.mark.parametrize("name", ["Edison township", "Wrentham town", "Montague township"])
def test_municipal_county_subdivision_is_kept(name):
    record = place_record_from_gazetteer(_gazetteer_row(name), "county_subdivision")

    assert record.kind == PlaceKind.COUNTY_SUBDIVISION


@pytest.mark.parametrize(
    "name", ["Autaugaville CCD", "District 1", "Unorganized Territory of X UT", "Precinct 4"]
)
def test_statistical_county_subdivision_is_dropped(name):
    assert place_record_from_gazetteer(_gazetteer_row(name), "county_subdivision") is None


def test_rows_outside_states_and_dc_are_dropped():
    row = _gazetteer_row("San Juan zona urbana", state="PR", lsad="62")

    assert place_record_from_gazetteer(row, "place") is None


def test_load_place_records_reads_committed_csv_format(tmp_path):
    path = tmp_path / "places.csv"
    path.write_text(
        "state,name,kind,land_area,latitude,longitude\n"
        "NJ,Edison township,COUNTY_SUBDIVISION,78000000,40.5,-74.4\n"
    )

    assert list(load_place_records(path)) == [
        PlaceRecord(
            state="NJ",
            name="Edison township",
            latitude=40.5,
            longitude=-74.4,
            kind=PlaceKind.COUNTY_SUBDIVISION,
            land_area=78000000,
        )
    ]
