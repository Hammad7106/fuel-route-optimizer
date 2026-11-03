"""Resolve user-supplied start and finish locations to coordinates.

Two forms are accepted, both resolved without calling an external API:

* ``"City, ST"``, e.g. ``"Chicago, IL"``, looked up in the place index;
  a trailing ``", USA"`` is ignored.
* ``"lat,lng"``, e.g. ``"41.8781,-87.6298"``, used as given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .exceptions import LocationNotFound
from .geocoding import Coordinates, PlaceIndex
from .us_states import US_STATE_CODES

_COORDINATES = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_COUNTRY_SUFFIX = re.compile(r",\s*(?:USA|US|United States)\s*$", re.IGNORECASE)

# Generous bounding box around the 50 states (Hawaii to Maine, Florida Keys
# to Alaska), to reject coordinates that are obviously outside the US.
_US_LATITUDES = (18.0, 72.0)
_US_LONGITUDES = (-180.0, -66.0)

_FORMAT_HINT = "Use 'City, ST' (e.g. 'Chicago, IL') or 'lat,lng' (e.g. '41.88,-87.63')."


@dataclass(frozen=True, slots=True)
class Location:
    label: str
    coordinates: Coordinates


def resolve_location(text: str, places: PlaceIndex) -> Location:
    """Resolve ``text`` to a US location, raising ``LocationNotFound`` if impossible."""
    text = text.strip()
    if match := _COORDINATES.match(text):
        return _from_coordinates(float(match[1]), float(match[2]), text)
    return _from_place_name(text, places)


def _from_coordinates(latitude: float, longitude: float, text: str) -> Location:
    if not (
        _US_LATITUDES[0] <= latitude <= _US_LATITUDES[1]
        and _US_LONGITUDES[0] <= longitude <= _US_LONGITUDES[1]
    ):
        raise LocationNotFound(f"'{text}' is outside the USA. {_FORMAT_HINT}")
    return Location(label=f"{latitude},{longitude}", coordinates=Coordinates(latitude, longitude))


def _from_place_name(text: str, places: PlaceIndex) -> Location:
    city, _, state = _COUNTRY_SUFFIX.sub("", text).rpartition(",")
    city, state = city.strip(), state.strip().upper()
    if not city or state not in US_STATE_CODES:
        raise LocationNotFound(f"Could not understand '{text}'. {_FORMAT_HINT}")

    place = places.lookup(city, state)
    if place is None:
        raise LocationNotFound(f"Could not find '{text}'. {_FORMAT_HINT}")
    return Location(label=f"{place.name}, {place.state}", coordinates=place.coordinates)
