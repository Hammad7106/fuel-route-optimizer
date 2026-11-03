"""Load fuel stations from the OPIS price file into the database.

Runs fully offline and replaces the table atomically, so it is safe to run
on every deploy.
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from routing.models import FuelStation
from routing.services.geocoding import PlaceIndex
from routing.services.stations import StationFileError, prepare_stations, read_station_file


class Command(BaseCommand):
    help = "Load and geocode fuel stations from the OPIS price CSV."

    def add_arguments(self, parser):
        parser.add_argument("--csv", type=Path, default=settings.FUEL_PRICES_CSV)
        parser.add_argument("--places", type=Path, default=settings.US_PLACES_FILE)

    def handle(self, *args, csv: Path, places: Path, verbosity: int, **options):
        for path in (csv, places):
            if not path.exists():
                raise CommandError(f"File not found: {path}")

        try:
            prepared = prepare_stations(read_station_file(csv), PlaceIndex.from_file(places))
        except StationFileError as exc:
            raise CommandError(str(exc)) from exc

        with transaction.atomic():
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(prepared.stations, batch_size=1000)

        self.stdout.write(
            f"Read {prepared.rows_read:,} rows: "
            f"{prepared.non_us_rows:,} outside the US, "
            f"{prepared.duplicates_merged:,} duplicates merged, "
            f"{prepared.unmatched_rows:,} not geocoded."
        )
        if verbosity > 1:
            for (city, state), count in prepared.unmatched.most_common():
                self.stdout.write(f"  not geocoded: {city}, {state} ({count})")
        self.stdout.write(
            self.style.SUCCESS(f"Loaded {len(prepared.stations):,} fuel stations.")
        )
