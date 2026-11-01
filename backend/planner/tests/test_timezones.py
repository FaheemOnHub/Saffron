from datetime import datetime

from django.test import SimpleTestCase

from planner.timezones import localize, timezone_name_at


class TimezoneLookupTests(SimpleTestCase):
    def test_cities_and_a_county_line(self):
        cases = [
            ((41.88, -87.63), "America/Chicago"),
            ((39.74, -104.99), "America/Denver"),
            ((28.61, 77.21), "Asia/Kolkata"),
            # Kansas splits between Central and Mountain about 40 miles apart.
            ((39.40, -101.05), "America/Chicago"),
            ((39.35, -101.71), "America/Denver"),
        ]
        for (lat, lng), expected in cases:
            with self.subTest(lat=lat, lng=lng):
                self.assertEqual(timezone_name_at(lat, lng), expected)

    def test_localize_follows_daylight_saving(self):
        summer = localize(datetime(2026, 7, 1, 8, 0), "America/Chicago")
        winter = localize(datetime(2026, 12, 1, 8, 0), "America/Chicago")
        self.assertEqual(summer.utcoffset().total_seconds() / 3600, -5)
        self.assertEqual(winter.utcoffset().total_seconds() / 3600, -6)
