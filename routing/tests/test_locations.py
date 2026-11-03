from django.test import SimpleTestCase

from routing.services.exceptions import LocationNotFound
from routing.services.geocoding import Coordinates, Place, PlaceIndex
from routing.services.locations import resolve_location

CHICAGO = Coordinates(41.8781, -87.6298)
PLACES = PlaceIndex({("IL", "CHICAGO"): Place("Chicago", "IL", CHICAGO)})


class ResolveLocationTests(SimpleTestCase):
    def test_resolves_city_and_state(self):
        location = resolve_location("Chicago, IL", PLACES)

        self.assertEqual(location.coordinates, CHICAGO)
        self.assertEqual(location.label, "Chicago, IL")

    def test_is_lenient_about_case_spacing_and_country(self):
        for text in ("chicago,il", "  CHICAGO ,  il ", "Chicago, IL, USA"):
            with self.subTest(text=text):
                self.assertEqual(resolve_location(text, PLACES).coordinates, CHICAGO)

    def test_accepts_coordinates(self):
        location = resolve_location("41.8781, -87.6298", PLACES)

        self.assertEqual(location.coordinates, CHICAGO)

    def test_rejects_coordinates_outside_the_us(self):
        with self.assertRaisesMessage(LocationNotFound, "outside the USA"):
            resolve_location("51.5072,-0.1276", PLACES)

    def test_rejects_unknown_city(self):
        with self.assertRaisesMessage(LocationNotFound, "Could not find 'Atlantis, IL'"):
            resolve_location("Atlantis, IL", PLACES)

    def test_rejects_unrecognized_formats(self):
        for text in ("Chicago", "Chicago, Illinois", "Toronto, ON", ", IL", ""):
            with self.subTest(text=text), self.assertRaises(LocationNotFound):
                resolve_location(text, PLACES)
