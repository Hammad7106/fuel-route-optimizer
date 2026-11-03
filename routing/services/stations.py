"""Read the OPIS fuel price file and prepare stations for the database.

The raw file needs three clean-up steps before it is usable:

* It includes Canadian stations, which are outside the service area.
* Many stations appear several times with different prices; each station
  is kept once, at its lowest price, as a cost-minimizing driver would pay.
* It has no coordinates; stations are placed at their city's location
  using the offline place index.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..models import FuelStation
from .geocoding import PlaceIndex
from .us_states import US_STATE_CODES

_COLUMNS = {
    "opis_id": "OPIS Truckstop ID",
    "name": "Truckstop Name",
    "address": "Address",
    "city": "City",
    "state": "State",
    "rack_id": "Rack ID",
    "retail_price": "Retail Price",
}


class StationFileError(ValueError):
    """The fuel price file is missing columns or has malformed rows."""


@dataclass(frozen=True, slots=True)
class StationRecord:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    rack_id: int
    retail_price: Decimal


@dataclass(slots=True)
class PreparedStations:
    stations: list[FuelStation]
    rows_read: int
    non_us_rows: int
    duplicates_merged: int
    unmatched: Counter[tuple[str, str]] = field(default_factory=Counter)

    @property
    def unmatched_rows(self) -> int:
        return sum(self.unmatched.values())


def read_station_file(path: Path) -> Iterator[StationRecord]:
    with path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        missing = set(_COLUMNS.values()) - set(reader.fieldnames or [])
        if missing:
            raise StationFileError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            yield _parse_row(row, line=reader.line_num)


def prepare_stations(records: Iterable[StationRecord], places: PlaceIndex) -> PreparedStations:
    """Filter to the US, merge duplicates and geocode, ready for ``bulk_create``."""
    rows_read = non_us_rows = 0
    cheapest: dict[int, StationRecord] = {}
    for record in records:
        rows_read += 1
        if record.state not in US_STATE_CODES:
            non_us_rows += 1
            continue
        current = cheapest.get(record.opis_id)
        if current is None or record.retail_price < current.retail_price:
            cheapest[record.opis_id] = record

    result = PreparedStations(
        stations=[],
        rows_read=rows_read,
        non_us_rows=non_us_rows,
        duplicates_merged=rows_read - non_us_rows - len(cheapest),
    )
    for record in cheapest.values():
        place = places.lookup(record.city, record.state)
        if place is None:
            result.unmatched[(record.city, record.state)] += 1
            continue
        result.stations.append(
            FuelStation(
                opis_id=record.opis_id,
                name=record.name,
                address=record.address,
                city=record.city,
                state=record.state,
                rack_id=record.rack_id,
                retail_price=record.retail_price,
                latitude=place.coordinates.latitude,
                longitude=place.coordinates.longitude,
            )
        )
    return result


def _parse_row(row: dict[str, str], line: int) -> StationRecord:
    values = {attr: row[column].strip() for attr, column in _COLUMNS.items()}
    try:
        return StationRecord(
            opis_id=int(values["opis_id"]),
            name=values["name"],
            address=values["address"],
            city=values["city"],
            state=values["state"].upper(),
            rack_id=int(values["rack_id"]),
            retail_price=Decimal(values["retail_price"]),
        )
    except (ValueError, InvalidOperation) as exc:
        raise StationFileError(f"Malformed row on line {line}: {exc}") from exc
