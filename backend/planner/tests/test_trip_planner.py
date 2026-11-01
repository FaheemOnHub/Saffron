from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import SimpleTestCase

from planner.checkpoints import METERS_PER_MILE
from planner.risk import RiskLevel
from planner.routing import Place, RouteStretch, TruckRoute
from planner.trip_planner import plan_trip
from planner.weather import WeatherReading

DEPARTURE = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
DALLAS = Place("Dallas, TX", 32.78, -96.80)
HOUSTON = Place("Houston, TX", 29.76, -95.37)


def straight_route(miles, hours, longitude):
    meters = miles * METERS_PER_MILE
    path = [(32.78 - i * 0.03, longitude) for i in range(101)]
    return TruckRoute(
        path=path, stretches=[RouteStretch(0, meters, hours * 3600)], distance_m=meters,
        duration_s=hours * 3600, departure_time=DEPARTURE,
        arrival_time=DEPARTURE + timedelta(hours=hours),
    )


def calm():
    return WeatherReading(5.0, 8.0, 0.0, 0.0, DEPARTURE)


def stormy():
    return WeatherReading(5.0, 8.0, 0.7, 0.0, DEPARTURE)  # Severe rain


@patch("planner.trip_planner.corridor_forecast", return_value="corridor-forecast")
@patch("planner.trip_planner.forecast_for")
@patch("planner.trip_planner.fetch_route_options")
@patch("planner.trip_planner.geocode_place", side_effect=[DALLAS, HOUSTON])
class PlanTripTests(SimpleTestCase):
    def test_weather_goes_to_the_right_route_and_safer_route_wins(self, _geocode, mock_routes, mock_forecast, _corridor):
        fast_but_stormy = straight_route(miles=50, hours=1, longitude=-96.8)
        slow_but_calm = straight_route(miles=50, hours=2, longitude=-96.5)
        mock_routes.return_value = [fast_but_stormy, slow_but_calm]
        # 25 mi spacing on 50 mi routes -> 3 checkpoints each, fetched in one call.
        mock_forecast.return_value = [stormy(), stormy(), stormy(), calm(), calm(), calm()]

        plan = plan_trip("Dallas", "Houston", DEPARTURE, 20_000, 25)

        self.assertEqual(mock_forecast.call_count, 1)
        self.assertEqual(len(mock_forecast.call_args.args[0]), 6)
        best, other = plan.routes
        self.assertIs(best.route, slow_but_calm)
        self.assertEqual(best.worst_level, RiskLevel.LOW)
        self.assertEqual(other.worst_level, RiskLevel.SEVERE)
        self.assertAlmostEqual(other.severe_miles, 50)
        self.assertTrue(best.is_recommended)

    def test_passes_inputs_through(self, mock_geocode, mock_routes, mock_forecast, mock_corridor):
        mock_routes.return_value = [straight_route(miles=50, hours=1, longitude=-96.8)]
        mock_forecast.return_value = [calm()] * 6

        plan = plan_trip("Dallas", "Houston", DEPARTURE, 42_000, 10)

        mock_geocode.assert_any_call("Dallas")
        mock_routes.assert_called_once_with(DALLAS, HOUSTON, DEPARTURE, 42_000)
        self.assertEqual(len(plan.routes[0].checkpoints), 6)  # 0,10,20,30,40,50
        self.assertEqual(plan.checkpoint_interval_miles, 10)
        self.assertEqual(plan.origin, DALLAS)
        mock_corridor.assert_called_once_with(mock_routes.return_value, DEPARTURE, 42_000)
        self.assertEqual(plan.corridor, "corridor-forecast")
