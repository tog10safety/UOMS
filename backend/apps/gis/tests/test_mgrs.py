import math
import random

from django.test import SimpleTestCase

from apps.gis.utils import MGRSError, latlon_to_mgrs, mgrs_to_latlon


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))


class MGRSRoundTripTests(SimpleTestCase):
    def test_round_trip_is_accurate_to_a_metre_across_the_globe(self):
        rng = random.Random(2026)
        for _ in range(3000):
            lat, lon = rng.uniform(-79.9, 83.9), rng.uniform(-179.99, 179.99)
            self.assertLess(metres((lat, lon), mgrs_to_latlon(latlon_to_mgrs(lat, lon))), 1.5, (lat, lon))

    def test_philippine_locations(self):
        for lat, lon in ((8.4822, 124.6472), (14.5995, 120.9842), (7.0731, 125.6128), (18.1960, 120.5930)):
            self.assertLess(metres((lat, lon), mgrs_to_latlon(latlon_to_mgrs(lat, lon))), 1.5)

    def test_accepts_spaces_case_and_coarser_grids(self):
        ref = latlon_to_mgrs(8.4822, 124.6472)
        compact, lower = ref.replace(' ', ''), ref.lower()
        self.assertEqual(mgrs_to_latlon(ref), mgrs_to_latlon(compact))
        self.assertEqual(mgrs_to_latlon(ref), mgrs_to_latlon(lower))
        zone_band, square, e, n = ref.split()
        coarse = mgrs_to_latlon(f'{zone_band}{square}{e[:3]}{n[:3]}')          # 100 m cell
        self.assertLess(metres(coarse, mgrs_to_latlon(ref)), 150)

    def test_bad_input_gives_a_readable_error(self):
        cases = {
            '': 'Enter an MGRS', 'hello': 'not a valid MGRS', '51P XQ 123 45': 'same number of digits',
            '61P XQ 1 1': 'zone 61', '51P ZZ 12345 67890': 'not a valid MGRS', '51N CQ 12345 67890': 'not valid for zone 51',
            '51P UH 12345 67890': 'does not exist in latitude band',
        }
        for text, fragment in cases.items():
            with self.assertRaises(MGRSError, msg=text) as ctx:
                mgrs_to_latlon(text)
            self.assertIn(fragment, str(ctx.exception), text)
        with self.assertRaises(MGRSError):
            mgrs_to_latlon(None)
