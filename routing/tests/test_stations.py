import tempfile
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase

from routing.services.geocoding import Coordinates, Place, PlaceIndex
from routing.services.stations import (
    StationFileError,
    StationRecord,
    prepare_stations,
    read_station_file,
)

from .factories import write_station_file


def record(opis_id=1, city="Tomah", state="WI", price="3.50"):
    return StationRecord(opis_id, f"Stop {opis_id}", "I-94", city, state, 100, Decimal(price))


PLACES = PlaceIndex({("WI", "TOMAH"): Place("Tomah", "WI", Coordinates(43.98, -90.50))})


class ReadStationFileTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "prices.csv"

    def test_parses_and_trims_rows(self):
        write_station_file(
            self.path, [[7, " WOODSHED ", "I-44", "Big Cabin", "ok", 307, "3.00733333"]]
        )

        (parsed,) = read_station_file(self.path)

        self.assertEqual(parsed.name, "WOODSHED")
        self.assertEqual(parsed.state, "OK")
        self.assertEqual(parsed.retail_price, Decimal("3.00733333"))

    def test_rejects_missing_columns(self):
        self.path.write_text("Truckstop Name,City\nA,B\n")

        with self.assertRaisesMessage(StationFileError, "missing columns"):
            list(read_station_file(self.path))

    def test_rejects_malformed_price(self):
        write_station_file(self.path, [[7, "A", "B", "C", "OK", 307, "n/a"]])

        with self.assertRaisesMessage(StationFileError, "line 2"):
            list(read_station_file(self.path))


class PrepareStationsTests(SimpleTestCase):
    def test_geocodes_station_to_its_city(self):
        result = prepare_stations([record()], PLACES)

        (station,) = result.stations
        self.assertEqual((station.latitude, station.longitude), (43.98, -90.50))

    def test_excludes_stations_outside_the_us(self):
        result = prepare_stations([record(state="ON")], PLACES)

        self.assertEqual(result.stations, [])
        self.assertEqual(result.non_us_rows, 1)

    def test_merges_duplicates_keeping_lowest_price(self):
        records = [record(price="3.90"), record(price="3.40"), record(price="3.70")]

        result = prepare_stations(records, PLACES)

        (station,) = result.stations
        self.assertEqual(station.retail_price, Decimal("3.40"))
        self.assertEqual(result.duplicates_merged, 2)

    def test_reports_stations_that_cannot_be_geocoded(self):
        result = prepare_stations([record(1), record(2, city="Atlantis")], PLACES)

        self.assertEqual(len(result.stations), 1)
        self.assertEqual(result.unmatched, {("Atlantis", "WI"): 1})
        self.assertEqual(result.unmatched_rows, 1)
