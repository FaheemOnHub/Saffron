from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import SimpleTestCase

from planner.checkpoints import METERS_PER_MILE, haversine_m
from planner.corridor import (
    CORRIDOR_HALF_WIDTH_MILES,
    FORECAST_HOUR_COUNT,
    MAX_GRID_POINTS,
    MIN_SPACING_MILES,
    corridor_forecast,
    corridor_grid,
)
from planner.risk import RiskLevel
from planner.routing import TruckRoute
from planner.weather import WeatherReading

DEPARTURE = datetime(2026, 11, 2, 8, 20, tzinfo=timezone.utc)


def route_along(points):
    return TruckRoute(points, [], 0, 0, DEPARTURE, DEPARTURE)


def east_bound(miles, latitude=40.0, start_lng=-100.0):
    """Points every mile heading due east."""
    degrees_per_mile = METERS_PER_MILE / haversine_m((latitude, 0), (latitude, 1))
    return [(latitude, start_lng + i * degrees_per_mile) for i in range(int(miles) + 1)]


def distance_to_route_miles(point, path):
    return min(haversine_m(point, route_point) for route_point in path) / METERS_PER_MILE


class CorridorGridTests(SimpleTestCase):
    def test_every_point_is_inside_the_corridor(self):
        path = east_bound(200)
        grid = corridor_grid([route_along(path)])
        self.assertTrue(grid.points)
        for point in grid.points:
            self.assertLessEqual(distance_to_route_miles(point, path), CORRIDOR_HALF_WIDTH_MILES + 0.5)

    def test_corridor_is_covered_on_both_sides(self):
        path = east_bound(200)
        grid = corridor_grid([route_along(path)])
        latitudes = [lat for lat, _ in grid.points]
        self.assertLess(min(latitudes), 40.0 - 0.2)  # ~14 mi south
        self.assertGreater(max(latitudes), 40.0 + 0.2)  # ~14 mi north

    def test_short_trip_uses_minimum_spacing(self):
        grid = corridor_grid([route_along(east_bound(15))])
        self.assertAlmostEqual(grid.spacing_m / METERS_PER_MILE, MIN_SPACING_MILES)
        self.assertLessEqual(len(grid.points), MAX_GRID_POINTS)

    def test_long_trip_widens_spacing_to_stay_in_budget(self):
        routes = [route_along(east_bound(1200, latitude=lat)) for lat in (38.0, 39.0, 40.0)]
        grid = corridor_grid(routes)
        self.assertLessEqual(len(grid.points), MAX_GRID_POINTS)
        self.assertGreater(len(grid.points), MAX_GRID_POINTS / 2)  # not wastefully sparse
        self.assertGreater(grid.spacing_m / METERS_PER_MILE, MIN_SPACING_MILES)

    def test_overlapping_routes_do_not_duplicate_points(self):
        path = east_bound(100)
        one = corridor_grid([route_along(path)])
        three = corridor_grid([route_along(path)] * 3)
        self.assertEqual(len(set(three.points)), len(three.points))
        self.assertLessEqual(len(three.points), MAX_GRID_POINTS)
        self.assertTrue(one.points)

    def test_no_routes(self):
        self.assertEqual(corridor_grid([]).points, [])


def reading(wind=5.0, rain=0.0, snow=0.0):
    return WeatherReading(wind, wind, rain, snow, DEPARTURE)


@patch("planner.corridor.hourly_forecasts")
class CorridorForecastTests(SimpleTestCase):
    def test_frames_start_at_departure_hour_in_utc(self, mock_hourly):
        mock_hourly.side_effect = lambda points, first_hour, count: [[reading()] * count for _ in points]
        india_departure = datetime(2026, 11, 2, 14, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
        forecast = corridor_forecast([route_along(east_bound(20))], india_departure, 0)

        first_hour = mock_hourly.call_args.args[1]
        self.assertEqual(first_hour, datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(len(forecast.frames), FORECAST_HOUR_COUNT)
        self.assertEqual(forecast.frames[1].hour - forecast.frames[0].hour, timedelta(hours=1))

    def test_frame_values_use_risk_rules_and_scores(self, mock_hourly):
        def fake(points, first_hour, count):
            # Point 0: 40 mph wind every hour. Point 1: no forecast after the first hour.
            return [[reading(wind=40.0)] * count] + [[reading(rain=0.3)] + [None] * (count - 1)] * (len(points) - 1)

        mock_hourly.side_effect = fake
        forecast = corridor_forecast([route_along(east_bound(20))], DEPARTURE, 45_000)
        first, later = forecast.frames[0], forecast.frames[5]

        self.assertEqual(first.risk_levels[0], RiskLevel.SEVERE)  # High wind raised by a 45,000 lb load
        self.assertEqual(first.wind_scores[0], 2.5)
        self.assertEqual(first.risk_levels[1], RiskLevel.HIGH)
        self.assertEqual(first.rain_scores[1], 2.2)
        self.assertIsNone(later.risk_levels[1])
        self.assertIsNone(later.wind_scores[1])

    def test_no_grid_means_no_weather_call(self, mock_hourly):
        forecast = corridor_forecast([], DEPARTURE, 0)
        self.assertEqual(forecast.frames, [])
        mock_hourly.assert_not_called()
