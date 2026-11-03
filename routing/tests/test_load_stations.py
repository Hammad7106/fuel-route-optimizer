import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase

from routing.models import FuelStation

from .factories import write_place_file, write_station_file


class LoadStationsCommandTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.places = write_place_file(
            self.dir / "places.csv.gz", [("OK", "Big Cabin", 36.5376, -95.2208)]
        )
        self.csv = write_station_file(
            self.dir / "prices.csv",
            [
                [7, "WOODSHED OF BIG CABIN", "I-44", "Big Cabin", "OK", 307, "3.10"],
                [7, "WOODSHED OF BIG CABIN", "I-44", "Big Cabin", "OK", 307, "3.00"],
                [8, "NOWHERE STOP", "I-1", "Atlantis", "OK", 307, "2.90"],
                [9, "CALGARY STOP", "Hwy 2", "Calgary", "AB", 100, "4.00"],
            ],
        )

    def load(self, **options):
        out = StringIO()
        call_command("load_stations", csv=self.csv, places=self.places, stdout=out, **options)
        return out.getvalue()

    def test_loads_geocoded_us_stations(self):
        output = self.load()

        station = FuelStation.objects.get()
        self.assertEqual(station.opis_id, 7)
        self.assertEqual(str(station.retail_price), "3.00000000")
        self.assertIn("Loaded 1 fuel stations", output)
        self.assertIn("1 outside the US, 1 duplicates merged, 1 not geocoded", output)

    def test_is_idempotent(self):
        self.load()
        self.load()

        self.assertEqual(FuelStation.objects.count(), 1)

    def test_verbose_output_lists_unmatched_cities(self):
        self.assertIn("not geocoded: Atlantis, OK (1)", self.load(verbosity=2))

    def test_missing_file_is_a_command_error(self):
        with self.assertRaisesMessage(CommandError, "File not found"):
            call_command("load_stations", csv=self.dir / "nope.csv", places=self.places)
