from datetime import datetime, timezone
from unittest.mock import Mock, patch

import flexpolyline
import requests
from django.test import SimpleTestCase, override_settings

from planner.routing import (
    Place,
    RoutingError,
    fetch_truck_routes,
    geocode_place,
    gross_weight_kg,
)

DALLAS = Place("Dallas, TX", 32.7767, -96.7970)
HOUSTON = Place("Houston, TX", 29.7604, -95.3698)
DEPARTURE = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)


def fake_response(json_body, status_code=200):
    response = Mock()
    response.ok = status_code < 400
    response.status_code = status_code
    response.json.return_value = json_body
    response.text = str(json_body)
    return response


def here_section(points, spans, length_m, duration_s, departs, arrives):
    return {
        "polyline": flexpolyline.encode(points),
        "spans": spans,
        "summary": {"length": length_m, "duration": duration_s},
        "departure": {"time": departs},
        "arrival": {"time": arrives},
    }


def here_route(duration_s):
    section = here_section(
        points=[(32.77, -96.79), (31.0, -96.0), (29.76, -95.36)],
        spans=[{"offset": 0, "length": 200_000, "duration": duration_s / 2},
               {"offset": 1, "length": 190_000, "duration": duration_s / 2}],
        length_m=390_000,
        duration_s=duration_s,
        departs="2026-11-02T08:00:00+00:00",
        arrives="2026-11-02T12:00:00+00:00",
    )
    return {"sections": [section]}


@override_settings(HERE_API_KEY="test-key")
class GeocodeTests(SimpleTestCase):
    @patch("planner.routing.requests.get")
    def test_returns_best_match(self, mock_get):
        mock_get.return_value = fake_response(
            {"items": [{"title": "Dallas, TX, United States", "position": {"lat": 32.77, "lng": -96.79}}]}
        )
        place = geocode_place("  Dallas ")
        self.assertEqual(place, Place("Dallas, TX, United States", 32.77, -96.79))
        self.assertEqual(mock_get.call_args.kwargs["params"]["q"], "Dallas")

    @patch("planner.routing.requests.get")
    def test_no_match_raises(self, mock_get):
        mock_get.return_value = fake_response({"items": []})
        with self.assertRaisesMessage(RoutingError, "Could not find"):
            geocode_place("Nowhereville")

    def test_blank_query_raises_without_calling_api(self):
        with patch("planner.routing.requests.get") as mock_get:
            with self.assertRaises(RoutingError):
                geocode_place("   ")
            mock_get.assert_not_called()


class ApiFailureTests(SimpleTestCase):
    @override_settings(HERE_API_KEY="")
    def test_missing_key_raises(self):
        with self.assertRaisesMessage(RoutingError, "HERE_API_KEY"):
            geocode_place("Dallas")

    @override_settings(HERE_API_KEY="test-key")
    @patch("planner.routing.requests.get")
    def test_http_error_includes_here_title(self, mock_get):
        mock_get.return_value = fake_response({"title": "Unauthorized"}, status_code=401)
        with self.assertRaisesMessage(RoutingError, "Unauthorized"):
            geocode_place("Dallas")

    @override_settings(HERE_API_KEY="test-key")
    @patch("planner.routing.requests.get")
    def test_auth_error_uses_error_description(self, mock_get):
        mock_get.return_value = fake_response(
            {"error": "Unauthorized", "error_description": "apiKey invalid. apiKey not found."}, status_code=401
        )
        with self.assertRaisesMessage(RoutingError, "(401): apiKey invalid"):
            geocode_place("Dallas")

    @override_settings(HERE_API_KEY="test-key")
    @patch("planner.routing.requests.get", side_effect=requests.ConnectionError("down"))
    def test_network_error_raises_routing_error(self, _mock_get):
        with self.assertRaisesMessage(RoutingError, "Could not reach HERE"):
            geocode_place("Dallas")


@override_settings(HERE_API_KEY="test-key")
class FetchTruckRoutesTests(SimpleTestCase):
    @patch("planner.routing.requests.get")
    def test_sends_truck_params(self, mock_get):
        mock_get.return_value = fake_response({"routes": [here_route(14_400)]})
        fetch_truck_routes(DALLAS, HOUSTON, DEPARTURE, load_weight_lb=20_000)
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["transportMode"], "truck")
        self.assertEqual(params["origin"], "32.7767,-96.797")
        self.assertEqual(params["departureTime"], "2026-11-02T08:00:00+00:00")
        self.assertEqual(params["vehicle[grossWeight]"], gross_weight_kg(20_000))

    @patch("planner.routing.requests.get")
    def test_parses_route_and_sorts_fastest_first(self, mock_get):
        mock_get.return_value = fake_response({"routes": [here_route(16_000), here_route(14_400)]})
        routes = fetch_truck_routes(DALLAS, HOUSTON, DEPARTURE, load_weight_lb=20_000)
        self.assertEqual([route.duration_s for route in routes], [14_400, 16_000])
        fastest = routes[0]
        self.assertEqual(len(fastest.path), 3)
        self.assertAlmostEqual(fastest.path[0][0], 32.77, places=4)
        self.assertEqual(fastest.distance_m, 390_000)
        self.assertEqual(fastest.departure_time, DEPARTURE)
        self.assertEqual([s.start_point_index for s in fastest.stretches], [0, 1])

    @patch("planner.routing.requests.get")
    def test_multiple_sections_join_into_one_path(self, mock_get):
        first = here_section([(1.0, 1.0), (2.0, 2.0)], [{"offset": 0, "length": 100, "duration": 10}],
                             100, 10, "2026-11-02T08:00:00+00:00", "2026-11-02T08:00:10+00:00")
        second = here_section([(2.0, 2.0), (3.0, 3.0)], [{"offset": 0, "length": 50, "duration": 5}],
                              50, 5, "2026-11-02T08:00:10+00:00", "2026-11-02T08:00:15+00:00")
        mock_get.return_value = fake_response({"routes": [{"sections": [first, second]}]})
        route = fetch_truck_routes(DALLAS, HOUSTON, DEPARTURE, load_weight_lb=0)[0]
        self.assertEqual(len(route.path), 4)
        self.assertEqual([s.start_point_index for s in route.stretches], [0, 2])
        self.assertEqual(route.distance_m, 150)
        self.assertEqual(route.duration_s, 15)
        self.assertEqual(route.arrival_time.isoformat(), "2026-11-02T08:00:15+00:00")

    @patch("planner.routing.requests.get")
    def test_no_routes_raises(self, mock_get):
        mock_get.return_value = fake_response({"routes": []})
        with self.assertRaisesMessage(RoutingError, "no truck route"):
            fetch_truck_routes(DALLAS, HOUSTON, DEPARTURE, load_weight_lb=0)

    def test_naive_departure_time_is_rejected(self):
        with self.assertRaises(ValueError):
            fetch_truck_routes(DALLAS, HOUSTON, datetime(2026, 11, 2, 8, 0), load_weight_lb=0)


class GrossWeightTests(SimpleTestCase):
    def test_adds_empty_truck_and_converts_to_kg(self):
        # 35,000 + 45,000 = 80,000 lb, the US federal gross limit.
        self.assertEqual(gross_weight_kg(45_000), 36_287)
