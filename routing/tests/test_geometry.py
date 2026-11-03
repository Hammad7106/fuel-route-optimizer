from django.test import SimpleTestCase

from routing.services.geometry import simplify_path


class SimplifyPathTests(SimpleTestCase):
    def test_collapses_points_on_a_straight_line(self):
        path = [(x / 10, 0.0) for x in range(11)]

        self.assertEqual(simplify_path(path, tolerance=0.01), [(0.0, 0.0), (1.0, 0.0)])

    def test_keeps_corners(self):
        path = [(0.0, 0.0), (0.5, 0.0), (1.0, 0.0), (1.0, 0.5), (1.0, 1.0)]

        self.assertEqual(
            simplify_path(path, tolerance=0.01), [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
        )

    def test_drops_wiggles_smaller_than_tolerance(self):
        path = [(0.0, 0.0), (0.5, 0.004), (1.0, 0.0)]

        self.assertEqual(simplify_path(path, tolerance=0.01), [(0.0, 0.0), (1.0, 0.0)])
        self.assertEqual(len(simplify_path(path, tolerance=0.001)), 3)

    def test_short_paths_are_unchanged(self):
        self.assertEqual(simplify_path([(0.0, 0.0), (1.0, 1.0)], tolerance=1), [(0.0, 0.0), (1.0, 1.0)])
        self.assertEqual(simplify_path([], tolerance=1), [])
