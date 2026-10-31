import csv
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from planner.geodata import US_STATE_CODES, PlaceIndex, load_place_records
from planner.models import Station

EXPECTED_HEADER = [
    "OPIS Truckstop ID",
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Rack ID",
    "Retail Price",
]


@dataclass
class StationRow:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    price_per_gallon: Decimal


def parse_price(raw: str) -> Decimal | None:
    try:
        price = Decimal(raw)
    except InvalidOperation:
        return None
    return price if price.is_finite() and price > 0 else None


def read_station_rows(path: Path, skipped: Counter):
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        if next(reader, None) != EXPECTED_HEADER:
            raise CommandError(f"Unexpected CSV header in {path}")
        for fields in reader:
            try:
                opis_id, name, address, city, state, _rack_id, raw_price = fields
                opis_id = int(opis_id)
            except ValueError as error:
                raise CommandError(f"Malformed row at line {reader.line_num}: {error}") from error
            state = state.strip().upper()
            if state not in US_STATE_CODES:
                skipped["outside_us"] += 1
                continue
            price = parse_price(raw_price.strip())
            if price is None:
                skipped["invalid_price"] += 1
                continue
            yield StationRow(opis_id, name.strip(), address.strip(), city.strip(), state, price)


def merge_by_station(rows):
    """One row per station; repeated price observations keep the highest price.

    The file has no dates, so the highest price is a conservative estimate rather
    than a guess at which observation is the latest.
    """
    stations = {}
    for row in rows:
        existing = stations.setdefault(row.opis_id, row)
        existing.price_per_gallon = max(existing.price_per_gallon, row.price_per_gallon)
    return stations


class Command(BaseCommand):
    help = "Load the fuel price CSV into Station rows, located at their town's coordinates."

    def add_arguments(self, parser):
        parser.add_argument("--fuel-csv", type=Path, default=settings.FUEL_PRICES_CSV)
        parser.add_argument("--places-csv", type=Path, default=settings.US_PLACES_CSV)

    def handle(self, *args, fuel_csv, places_csv, **options):
        skipped = Counter()
        rows = merge_by_station(read_station_rows(fuel_csv, skipped))
        places = PlaceIndex(load_place_records(places_csv))

        stations, unlocated = [], Counter()
        for row in rows.values():
            place = places.resolve(row.city, row.state)
            if place is None:
                unlocated[f"{row.city}, {row.state}"] += 1
                continue
            stations.append(
                Station(**vars(row), latitude=place.latitude, longitude=place.longitude)
            )

        with transaction.atomic():
            Station.objects.all().delete()
            Station.objects.bulk_create(stations, batch_size=500)

        self._report(len(stations), skipped, unlocated)

    def _report(self, imported, skipped, unlocated):
        self.stdout.write(f"Stations imported: {imported}")
        self.stdout.write(f"Rows outside the US skipped: {skipped['outside_us']}")
        self.stdout.write(f"Rows with an invalid price skipped: {skipped['invalid_price']}")
        self.stdout.write(f"Stations without a known town (excluded): {unlocated.total()}")
        for town, count in unlocated.most_common():
            self.stdout.write(f"  {town}: {count}")
