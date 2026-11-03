"""Build the offline place index from public gazetteers.

Sources, in order of preference:

1. US Census Gazetteer, places: incorporated places and CDPs.
2. US Census Gazetteer, county subdivisions: towns and townships
   (e.g. Mahwah, NJ), which the places file omits.
3. GeoNames populated places: unincorporated communities such as
   Breezewood, PA, which the Census does not list but truck stops use as
   their postal city.

When several sources know the same (state, name), the most preferred wins.
"""

from __future__ import annotations

import csv
import gzip
import io
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from .geocoding import PLACE_INDEX_FIELDS, Coordinates, normalize_place_name
from .us_states import US_STATE_CODES

_CENSUS_PREFIX = re.compile(r"^(?:City|Town|Village|Borough) of ")
_PARENTHETICAL = re.compile(r"\s*\(.*\)$")

# GeoNames feature codes for places that no longer exist.
_DEFUNCT_FEATURE_CODES = frozenset({"PPLH", "PPLQ", "PPLW"})


class Source(IntEnum):
    """Place sources, most preferred first."""

    CENSUS_PLACES = 0
    CENSUS_COUNTY_SUBDIVISIONS = 1
    GEONAMES = 2


@dataclass(frozen=True, slots=True)
class PlaceCandidate:
    state: str
    name: str
    coordinates: Coordinates
    source: Source
    is_alias: bool = False
    # Breaks ties within a source (land area or population); larger wins.
    weight: float = 0.0

    @property
    def rank(self) -> tuple[int, bool, float]:
        return (self.source, self.is_alias, -self.weight)


def census_name_variants(name: str) -> list[str]:
    """Return the names a Census place is known by, canonical name first.

    Census names carry a legal-status suffix ("Tomah city", "Abanda CDP"),
    and consolidated governments use compound names ("Augusta-Richmond
    County consolidated government (balance)"). The canonical name drops
    those; the aliases ("Augusta", "Boise" for "Boise City") cover how
    people write such places.
    """
    name = _CENSUS_PREFIX.sub("", _PARENTHETICAL.sub("", name.strip()))
    words = name.split()
    while len(words) > 1 and (words[-1].islower() or words[-1] == "CDP"):
        words.pop()
    canonical = " ".join(words)

    variants = [canonical]
    if "-" in canonical:
        variants.append(canonical.split("-", 1)[0])
    if canonical.endswith(" City"):
        variants.append(canonical.removesuffix(" City"))
    return variants


def parse_census_gazetteer(lines: Iterable[str], source: Source) -> Iterator[PlaceCandidate]:
    """Parse a tab-separated Census Gazetteer file (places or county subdivisions)."""
    reader = csv.DictReader(lines, delimiter="\t")
    # Census pads the last header and the values in its column with spaces.
    reader.fieldnames = [field.strip() for field in reader.fieldnames or []]
    for row in reader:
        state = row["USPS"]
        if state not in US_STATE_CODES:
            continue
        coordinates = Coordinates(float(row["INTPTLAT"]), float(row["INTPTLONG"]))
        for position, name in enumerate(census_name_variants(row["NAME"])):
            yield PlaceCandidate(
                state=state,
                name=name,
                coordinates=coordinates,
                source=source,
                is_alias=position > 0,
                weight=float(row["ALAND"]),
            )


def parse_geonames(lines: Iterable[str]) -> Iterator[PlaceCandidate]:
    """Parse a GeoNames country dump (e.g. ``US.txt``), keeping populated places."""
    for line in lines:
        fields = line.rstrip("\n").split("\t")
        name, feature_class, feature_code, state = fields[1], fields[6], fields[7], fields[10]
        if (
            feature_class != "P"
            or feature_code in _DEFUNCT_FEATURE_CODES
            or "(historical)" in name
            or state not in US_STATE_CODES
        ):
            continue
        yield PlaceCandidate(
            state=state,
            name=name,
            coordinates=Coordinates(float(fields[4]), float(fields[5])),
            source=Source.GEONAMES,
            weight=float(fields[14] or 0),
        )


def select_best(candidates: Iterable[PlaceCandidate]) -> dict[tuple[str, str], PlaceCandidate]:
    """Keep the most preferred candidate for each (state, normalized name)."""
    best: dict[tuple[str, str], PlaceCandidate] = {}
    for candidate in candidates:
        key = (candidate.state, normalize_place_name(candidate.name))
        if not key[1]:
            continue
        current = best.get(key)
        if current is None or candidate.rank < current.rank:
            best[key] = candidate
    return best


def write_place_index(path: Path, places: dict[tuple[str, str], PlaceCandidate]) -> None:
    """Write the index as gzipped CSV, sorted and timestamp-free so rebuilds are reproducible."""
    with (
        gzip.GzipFile(path, "wb", mtime=0) as raw,
        io.TextIOWrapper(raw, encoding="utf-8", newline="") as file,
    ):
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(PLACE_INDEX_FIELDS)
        for (state, key), place in sorted(places.items()):
            writer.writerow(
                [
                    state,
                    key,
                    place.name,
                    f"{place.coordinates.latitude:.5f}",
                    f"{place.coordinates.longitude:.5f}",
                ]
            )
