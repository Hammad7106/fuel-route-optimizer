"""Builders for small test data files."""

import csv
from pathlib import Path

from routing.services.geocoding import Coordinates
from routing.services.place_sources import PlaceCandidate, Source, select_best, write_place_index

STATION_HEADER = [
    "OPIS Truckstop ID",
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Rack ID",
    "Retail Price",
]


def write_place_file(path: Path, places: list[tuple[str, str, float, float]]) -> Path:
    """Write a place index from (state, name, latitude, longitude) tuples."""
    candidates = [
        PlaceCandidate(state, name, Coordinates(lat, lon), Source.CENSUS_PLACES)
        for state, name, lat, lon in places
    ]
    write_place_index(path, select_best(candidates))
    return path


def write_station_file(path: Path, rows: list[list[object]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(STATION_HEADER)
        writer.writerows(rows)
    return path
