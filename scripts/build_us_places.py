"""Build data/us_places.csv from the Census Gazetteer national files.

Usage:
    python scripts/build_us_places.py PLACES_TXT COUSUBS_TXT data/us_places.csv

Inputs (public domain), unzipped from
https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/
    2025_Gaz_place_national.zip and 2025_Gaz_cousubs_national.zip
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planner.geodata import PLACE_CSV_FIELDS, place_record_from_gazetteer  # noqa: E402


def read_records(path, source):
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="|"):
            row = {key.strip(): value.strip() for key, value in row.items()}
            record = place_record_from_gazetteer(row, source)
            if record is not None:
                yield record


def main(places_path, cousubs_path, output_path):
    count = 0
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(PLACE_CSV_FIELDS)
        for path, source in ((places_path, "place"), (cousubs_path, "county_subdivision")):
            for record in read_records(path, source):
                writer.writerow(
                    [
                        record.state,
                        record.name,
                        record.kind.name,
                        record.land_area,
                        record.latitude,
                        record.longitude,
                    ]
                )
                count += 1
    print(f"Wrote {count} places to {output_path}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
