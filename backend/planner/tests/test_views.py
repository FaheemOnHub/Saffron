from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse

from planner.assessment import assess_route, rank_routes, rate_checkpoints
from planner.checkpoints import place_checkpoints
from planner.corridor import CorridorForecast, CorridorGrid, HeatmapFrame
from planner.routing import NoRouteError, PlaceNotFoundError, Place, RoutingError
from planner.trip_planner import TripPlan
from planner.weather import WeatherError, WeatherReading
from planner.tests.test_trip_planner import straight_route


def future(hours=2):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def valid_params(**overrides):
    params = {
        "origin": "Dallas, TX",
        "destination": "Houston, TX",
        "departure_time": future(),
        "load_weight_lb": "42000",
        "checkpoint_interval_miles": "25",
    }
    params.update(overrides)
    return params


def sample_plan():
    route = straight_route(miles=50, hours=1, longitude=-96.8)
    checkpoints = place_checkpoints(route, 25)
    readings = [WeatherReading(40.0, 52.0, 0.0, 0.0, route.departure_time)] + [None] * (len(checkpoints) - 1)
    assessment = assess_route(route, rate_checkpoints(checkpoints, readings, 42_000))
    return TripPlan(
        origin=Place("Dallas, TX, United States", 32.78, -96.8),
        destination=Place("Houston, TX, United States", 29.76, -95.37),
        load_weight_lb=42_000,
        checkpoint_interval_miles=25,
        routes=rank_routes([assessment]),
        corridor=CorridorForecast(
            grid=CorridorGrid(points=[(32.5, -96.6), (31.0, -96.0)], spacing_m=9656),
            frames=[
                HeatmapFrame(route.departure_time, [3, None], [2.5, None], [0.0, None], [0.0, None]),
                HeatmapFrame(route.departure_time, [1, 0], [1.2, 0.4], [0.0, 0.0], [0.0, 0.0]),
            ],
        ),
    )


class TripPlanValidationTests(SimpleTestCase):
    url = reverse("trip-plan")

    def assert_field_error(self, field, **overrides):
        with patch("planner.views.plan_trip") as mock_plan:
            response = self.client.get(self.url, valid_params(**overrides))
            mock_plan.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertIn(field, response.json()["errors"])

    def test_missing_and_blank_places(self):
        self.assert_field_error("origin", origin="   ")
        self.assert_field_error("destination", destination="")

    def test_overlong_place(self):
        self.assert_field_error("origin", origin="x" * 201)

    def test_same_origin_and_destination(self):
        self.assert_field_error("destination", destination="dallas, tx")

    def test_departure_formats_and_window(self):
        self.assert_field_error("departure_time", departure_time="tomorrow morning")
        self.assert_field_error("departure_time", departure_time="2026-11-02T08:00:00")  # no timezone
        self.assert_field_error("departure_time", departure_time=future(hours=-3))
        self.assert_field_error("departure_time", departure_time=future(hours=24 * 8))

    def test_recent_past_departure_is_allowed(self):
        with patch("planner.views.plan_trip", return_value=sample_plan()):
            response = self.client.get(self.url, valid_params(departure_time=future(hours=-0.5)))
        self.assertEqual(response.status_code, 200)

    def test_load_weight_bounds(self):
        self.assert_field_error("load_weight_lb", load_weight_lb="heavy")
        self.assert_field_error("load_weight_lb", load_weight_lb="-1")
        self.assert_field_error("load_weight_lb", load_weight_lb="80001")
        self.assert_field_error("load_weight_lb", load_weight_lb="nan")

    def test_checkpoint_interval_options(self):
        self.assert_field_error("checkpoint_interval_miles", checkpoint_interval_miles="30")
        self.assert_field_error("checkpoint_interval_miles", checkpoint_interval_miles="ten")

    def test_interval_defaults_to_25(self):
        params = valid_params()
        del params["checkpoint_interval_miles"]
        with patch("planner.views.plan_trip", return_value=sample_plan()) as mock_plan:
            self.client.get(self.url, params)
        self.assertEqual(mock_plan.call_args.kwargs["checkpoint_interval_miles"], 25)

    def test_post_is_not_allowed(self):
        self.assertEqual(self.client.post(self.url, valid_params()).status_code, 405)


class TripPlanErrorMappingTests(SimpleTestCase):
    url = reverse("trip-plan")

    def status_for(self, error):
        with patch("planner.views.plan_trip", side_effect=error):
            response = self.client.get(self.url, valid_params())
        return response.status_code, response.json()["detail"]

    def test_unknown_place_is_client_error(self):
        self.assertEqual(self.status_for(PlaceNotFoundError("Could not find 'Atlantis'")),
                         (400, "Could not find 'Atlantis'"))

    def test_no_route_is_unprocessable(self):
        self.assertEqual(self.status_for(NoRouteError("no truck route"))[0], 422)

    def test_upstream_failures_are_bad_gateway(self):
        self.assertEqual(self.status_for(RoutingError("HERE down"))[0], 502)
        self.assertEqual(self.status_for(WeatherError("Open-Meteo down"))[0], 502)


class TripPlanResponseTests(SimpleTestCase):
    url = reverse("trip-plan")

    def test_response_shape(self):
        with patch("planner.views.plan_trip", return_value=sample_plan()) as mock_plan:
            response = self.client.get(self.url, valid_params())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_plan.call_args.kwargs["load_weight_lb"], 42_000)
        body = response.json()

        self.assertEqual(body["origin"]["label"], "Dallas, TX, United States")
        self.assertEqual([level["key"] for level in body["risk_levels"]],
                         ["low", "moderate", "high", "severe", "no_travel"])

        self.assertEqual([rule["key"] for rule in body["ranking_rules"]],
                         ["no_travel_miles", "severe_miles", "high_miles", "average_risk", "travel_time"])

        route = body["routes"][0]
        self.assertEqual(route["id"], "route-1")
        self.assertEqual(route["highways"], [])
        self.assertIsNone(route["beats_next_on"])
        self.assertTrue(route["is_recommended"])
        self.assertFalse(route["is_detour"])
        self.assertEqual(route["distance_miles"], 50.0)
        self.assertEqual(len(route["path"]), 101)

        first, second = route["checkpoints"][:2]
        # 40 mph wind + 42,000 lb load -> Severe via the load rule.
        self.assertEqual(first["risk"]["level"], "severe")
        self.assertTrue(first["risk"]["raised_by_load"])
        self.assertEqual(first["weather"]["wind_gust_mph"], 52.0)
        self.assertFalse(first["gust_warning"])  # wind already High, so no extra warning
        self.assertFalse(second["forecast_available"])
        self.assertIsNone(second["risk"])

        summary = route["risk_summary"]
        self.assertEqual(summary["worst_level"], "severe")
        self.assertEqual(summary["miles_by_level"]["severe"], 12.5)
        self.assertEqual(summary["unknown_miles"], 37.5)

    def test_corridor_forecast_shape(self):
        with patch("planner.views.plan_trip", return_value=sample_plan()):
            corridor = self.client.get(self.url, valid_params()).json()["corridor_forecast"]
        self.assertEqual(corridor["points"], [[32.5, -96.6], [31.0, -96.0]])
        self.assertEqual(len(corridor["hours"]), 2)
        self.assertEqual(corridor["frames"]["risk"], [[3, None], [1, 0]])
        self.assertEqual(corridor["frames"]["wind"][0], [2.5, None])

    def test_large_responses_are_gzipped(self):
        with patch("planner.views.plan_trip", return_value=sample_plan()):
            response = self.client.get(self.url, valid_params(), HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(response.headers.get("Content-Encoding"), "gzip")


class HealthTests(SimpleTestCase):
    def test_health_is_ok(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
