from django.test import SimpleTestCase

from routing.services.geocoding import Coordinates
from routing.services.place_sources import (
    PlaceCandidate,
    Source,
    census_name_variants,
    parse_census_gazetteer,
    parse_geonames,
    select_best,
)

CENSUS_HEADER = (
    "USPS\tGEOID\tANSICODE\tNAME\tLSAD\tFUNCSTAT\tALAND\tAWATER"
    "\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG                \n"
)


def census_line(state: str, name: str, lat: float, lon: float, land: int = 1000) -> str:
    return f"{state}\t0\t0\t{name}\t25\tA\t{land}\t0\t0\t0\t{lat}\t{lon}      \n"


def geonames_line(name: str, state: str, feature_code: str = "PPL", population: int = 0) -> str:
    fields = ["1", name, name, "", "40.0", "-75.0", "P", feature_code, "US", "", state]
    fields += ["", "", "", str(population), "", "", "America/New_York", "2020-01-01"]
    return "\t".join(fields) + "\n"


class CensusNameVariantsTests(SimpleTestCase):
    def test_strips_legal_status_suffix(self):
        self.assertEqual(census_name_variants("Tomah city"), ["Tomah"])
        self.assertEqual(census_name_variants("Abanda CDP"), ["Abanda"])
        self.assertEqual(census_name_variants("Mahwah township"), ["Mahwah"])

    def test_keeps_capitalized_words(self):
        self.assertEqual(census_name_variants("Big Cabin town"), ["Big Cabin"])

    def test_strips_prefix(self):
        self.assertEqual(census_name_variants("Town of Pecos city"), ["Pecos"])

    def test_consolidated_government_gets_short_alias(self):
        self.assertEqual(
            census_name_variants("Augusta-Richmond County consolidated government (balance)"),
            ["Augusta-Richmond County", "Augusta"],
        )

    def test_city_suffix_gets_alias(self):
        self.assertEqual(census_name_variants("Boise City city"), ["Boise City", "Boise"])


class ParseCensusGazetteerTests(SimpleTestCase):
    def test_parses_rows_and_skips_territories(self):
        lines = [
            CENSUS_HEADER,
            census_line("WI", "Tomah city", 43.98, -90.50),
            census_line("PR", "Adjuntas zona urbana", 18.16, -66.72),
        ]

        candidates = list(parse_census_gazetteer(lines, Source.CENSUS_PLACES))

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].name, "Tomah")
        self.assertEqual(candidates[0].coordinates, Coordinates(43.98, -90.50))

    def test_marks_aliases(self):
        lines = [CENSUS_HEADER, census_line("ID", "Boise City city", 43.6, -116.2)]

        candidates = list(parse_census_gazetteer(lines, Source.CENSUS_PLACES))

        self.assertEqual([c.is_alias for c in candidates], [False, True])


class ParseGeonamesTests(SimpleTestCase):
    def test_keeps_only_current_us_populated_places(self):
        lines = [
            geonames_line("Breezewood", "PA"),
            geonames_line("Ghost Town", "PA", feature_code="PPLQ"),
            geonames_line("Old Mill (historical)", "PA"),
            geonames_line("San Juan", "PR"),
        ]

        names = [c.name for c in parse_geonames(lines)]

        self.assertEqual(names, ["Breezewood"])


class SelectBestTests(SimpleTestCase):
    def candidate(self, source, *, is_alias=False, weight=0.0, lat=0.0):
        return PlaceCandidate("GA", "Augusta", Coordinates(lat, 0.0), source, is_alias, weight)

    def test_prefers_more_trusted_source(self):
        best = select_best(
            [self.candidate(Source.GEONAMES, lat=2), self.candidate(Source.CENSUS_PLACES, lat=1)]
        )

        self.assertEqual(best[("GA", "AUGUSTA")].source, Source.CENSUS_PLACES)

    def test_prefers_canonical_name_over_alias_from_same_source(self):
        best = select_best(
            [
                self.candidate(Source.CENSUS_PLACES, is_alias=True, lat=1),
                self.candidate(Source.CENSUS_PLACES, lat=2),
            ]
        )

        self.assertFalse(best[("GA", "AUGUSTA")].is_alias)

    def test_breaks_ties_by_weight(self):
        best = select_best(
            [
                self.candidate(Source.GEONAMES, weight=10, lat=1),
                self.candidate(Source.GEONAMES, weight=5000, lat=2),
            ]
        )

        self.assertEqual(best[("GA", "AUGUSTA")].coordinates.latitude, 2)
