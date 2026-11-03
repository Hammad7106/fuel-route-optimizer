import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from routing.services.geocoding import Coordinates, PlaceIndex, normalize_place_name

from .factories import write_place_file


class NormalizePlaceNameTests(SimpleTestCase):
    def test_ignores_case_spacing_and_punctuation(self):
        self.assertEqual(normalize_place_name("Mc Calla"), normalize_place_name("MCCALLA"))
        self.assertEqual(normalize_place_name("De Forest"), normalize_place_name("DeForest"))
        self.assertEqual(normalize_place_name("O'Fallon"), normalize_place_name("OFallon"))

    def test_expands_abbreviations(self):
        self.assertEqual(normalize_place_name("St. Louis"), normalize_place_name("Saint Louis"))
        self.assertEqual(normalize_place_name("Ft Worth"), normalize_place_name("Fort Worth"))
        self.assertEqual(normalize_place_name("Mt. Vernon"), normalize_place_name("Mount Vernon"))
        self.assertEqual(
            normalize_place_name("Sault Ste. Marie"), normalize_place_name("Sault Sainte Marie")
        )

    def test_does_not_expand_abbreviations_inside_words(self):
        self.assertEqual(normalize_place_name("Stanton"), "STANTON")

    def test_strips_accents(self):
        self.assertEqual(normalize_place_name("Cañon City"), normalize_place_name("Canon City"))


class PlaceIndexTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        path = write_place_file(
            Path(cls.tmp.name) / "places.csv.gz",
            [("OK", "Big Cabin", 36.5376, -95.2208), ("MO", "St. Louis", 38.6358, -90.2451)],
        )
        cls.index = PlaceIndex.from_file(path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        super().tearDownClass()

    def test_lookup_returns_coordinates(self):
        place = self.index.lookup("Big Cabin", "OK")

        self.assertEqual(place.coordinates, Coordinates(36.5376, -95.2208))

    def test_lookup_is_lenient_about_spelling(self):
        self.assertIsNotNone(self.index.lookup("SAINT LOUIS", " mo "))

    def test_lookup_requires_matching_state(self):
        self.assertIsNone(self.index.lookup("Big Cabin", "TX"))

    def test_lookup_unknown_place_returns_none(self):
        self.assertIsNone(self.index.lookup("Atlantis", "OK"))
