"""Download public gazetteers and build the offline US place index.

This is a one-off data build; its output, ``data/us_places.csv.gz``, is
committed so the app never needs these downloads at runtime.
"""

import io
import zipfile
from collections.abc import Callable, Iterable, Iterator
from itertools import chain
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from routing.services.place_sources import (
    PlaceCandidate,
    Source,
    parse_census_gazetteer,
    parse_geonames,
    select_best,
    write_place_index,
)

CENSUS_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/{name}.zip"

Parser = Callable[[Iterable[str]], Iterator[PlaceCandidate]]

SOURCES: dict[Source, tuple[str, str, Parser]] = {
    Source.CENSUS_PLACES: (
        CENSUS_URL.format(name="2024_Gaz_place_national"),
        "2024_Gaz_place_national.txt",
        lambda lines: parse_census_gazetteer(lines, Source.CENSUS_PLACES),
    ),
    Source.CENSUS_COUNTY_SUBDIVISIONS: (
        CENSUS_URL.format(name="2024_Gaz_cousubs_national"),
        "2024_Gaz_cousubs_national.txt",
        lambda lines: parse_census_gazetteer(lines, Source.CENSUS_COUNTY_SUBDIVISIONS),
    ),
    Source.GEONAMES: (
        "https://download.geonames.org/export/dump/US.zip",
        "US.txt",
        parse_geonames,
    ),
}

DOWNLOAD_TIMEOUT_SECONDS = 60


class Command(BaseCommand):
    help = "Build data/us_places.csv.gz from the US Census Gazetteer and GeoNames."

    def add_arguments(self, parser):
        parser.add_argument(
            "--download-dir",
            type=Path,
            default=Path(".cache/places"),
            help="Where source archives are stored; existing files are reused.",
        )
        parser.add_argument("--output", type=Path, default=settings.US_PLACES_FILE)

    def handle(self, *args, download_dir: Path, output: Path, **options):
        download_dir.mkdir(parents=True, exist_ok=True)
        candidates = chain.from_iterable(
            self._read_source(source, download_dir) for source in SOURCES
        )
        places = select_best(candidates)
        write_place_index(output, places)
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(places):,} places to {output}"))

    def _read_source(self, source: Source, download_dir: Path) -> Iterator[PlaceCandidate]:
        url, member, parse = SOURCES[source]
        archive = download_dir / url.rsplit("/", 1)[-1]
        if not archive.exists():
            self.stdout.write(f"Downloading {url}")
            _download(url, archive)
        with zipfile.ZipFile(archive) as zf, zf.open(member) as raw:
            yield from parse(io.TextIOWrapper(raw, encoding="utf-8", newline=""))


def _download(url: str, destination: Path) -> None:
    partial = destination.with_suffix(".part")
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        response.raise_for_status()
        with partial.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1 << 20):
                file.write(chunk)
    partial.rename(destination)
