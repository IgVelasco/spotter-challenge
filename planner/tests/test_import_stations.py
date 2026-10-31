from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from planner.models import Station

HEADER = "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
PLACES = (
    "state,name,kind,land_area,latitude,longitude\n"
    "OK,Big Cabin town,INCORPORATED,1000,36.53,-95.22\n"
    "WI,Tomah city,INCORPORATED,1000,43.98,-90.50\n"
    "AZ,Gila Bend town,INCORPORATED,1000,32.95,-112.72\n"
)


@pytest.fixture
def run_import(tmp_path):
    places = tmp_path / "places.csv"
    places.write_text(PLACES)

    def run(fuel_rows):
        fuel = tmp_path / "fuel.csv"
        fuel.write_text(HEADER + fuel_rows, newline="")
        out = StringIO()
        call_command("import_stations", fuel_csv=fuel, places_csv=places, stdout=out)
        return out.getvalue()

    return run


@pytest.mark.django_db
def test_imports_us_station_with_town_coordinates(run_import):
    run_import('7,WOODSHED OF BIG CABIN,"I-44, EXIT 283 & US-69",Big Cabin,OK,307,3.00733333\r\n')

    station = Station.objects.get()
    assert station.opis_id == 7
    assert station.name == "WOODSHED OF BIG CABIN"
    assert station.address == "I-44, EXIT 283 & US-69"
    assert station.city == "Big Cabin"
    assert station.state == "OK"
    assert station.price_per_gallon == Decimal("3.00733333")
    assert (station.latitude, station.longitude) == (36.53, -95.22)


@pytest.mark.django_db
def test_trims_whitespace_around_fields(run_import):
    run_import("9,  KWIK TRIP  ,I-94,Tomah                 , wi ,420,3.28733333\n")

    station = Station.objects.get()
    assert (station.name, station.city, station.state) == ("KWIK TRIP", "Tomah", "WI")


@pytest.mark.django_db
def test_repeated_station_keeps_one_row_with_highest_price(run_import):
    output = run_import(
        "20,PILOT TRAVEL CENTER #1243,I-8,Gila Bend,AZ,930,3.899\n"
        "20,PILOT #1243,I-8,Gila Bend,AZ,930,4.10\n"
        "20,PILOT #1243,I-8,Gila Bend,AZ,930,3.75\n"
    )

    station = Station.objects.get()
    assert station.price_per_gallon == Decimal("4.10")
    assert station.name == "PILOT TRAVEL CENTER #1243"
    assert "Stations imported: 1" in output


@pytest.mark.django_db
def test_skips_canadian_rows(run_import):
    output = run_import(
        "7,WOODSHED,I-44,Big Cabin,OK,307,3.00\n500,PETRO CANADA,HWY 1,Calgary,AB,1,1.50\n"
    )

    assert list(Station.objects.values_list("opis_id", flat=True)) == [7]
    assert "Rows outside the US skipped: 1" in output


@pytest.mark.django_db
def test_excludes_and_reports_stations_without_known_town(run_import):
    output = run_import(
        "7,WOODSHED,I-44,Big Cabin,OK,307,3.00\n8,BREEZEWOOD TRAVEL,I-70,Breezewood,PA,1,3.50\n"
    )

    assert list(Station.objects.values_list("opis_id", flat=True)) == [7]
    assert "Stations without a known town (excluded): 1" in output
    assert "Breezewood, PA" in output


@pytest.mark.django_db
@pytest.mark.parametrize("price", ["0", "-3.10", "abc", "NaN", "Infinity"])
def test_rejects_invalid_price_rows(run_import, price):
    output = run_import(f"7,WOODSHED,I-44,Big Cabin,OK,307,{price}\n")

    assert not Station.objects.exists()
    assert "Rows with an invalid price skipped: 1" in output


@pytest.mark.django_db
def test_reimport_replaces_previous_stations(run_import):
    run_import("7,WOODSHED,I-44,Big Cabin,OK,307,3.00\n")
    run_import("9,KWIK TRIP,I-94,Tomah,WI,420,3.20\n")

    assert list(Station.objects.values_list("opis_id", flat=True)) == [9]


@pytest.mark.django_db
def test_unexpected_header_aborts_without_touching_existing_stations(run_import, tmp_path):
    run_import("7,WOODSHED,I-44,Big Cabin,OK,307,3.00\n")
    bad = tmp_path / "bad.csv"
    bad.write_text("id,name,price\n1,X,3.00\n")

    with pytest.raises(CommandError, match="Unexpected CSV header"):
        call_command(
            "import_stations", fuel_csv=bad, places_csv=tmp_path / "places.csv", stdout=StringIO()
        )

    assert Station.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("bad_row", ["8,ONLY,FOUR,FIELDS\n", "X9,BAD ID,I-94,Tomah,WI,420,3.20\n"])
def test_malformed_row_aborts_naming_line_and_keeps_existing_stations(run_import, bad_row):
    run_import("7,WOODSHED,I-44,Big Cabin,OK,307,3.00\n")

    with pytest.raises(CommandError, match="line 3"):
        run_import("9,KWIK TRIP,I-94,Tomah,WI,420,3.20\n" + bad_row)

    assert list(Station.objects.values_list("opis_id", flat=True)) == [7]
