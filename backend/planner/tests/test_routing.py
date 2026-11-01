from datetime import datetime, timezone
from math import cos, radians
from unittest.mock import Mock, patch

import flexpolyline
import requests
from django.test import SimpleTestCase, override_settings

from planner.routing import (
    Place,
    RoutingError,
    TruckRoute,
    _detour_point,
    _mostly_same_road,
    fetch_route_options,
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
    def test_via_point_is_sent_as_pass_through(self, mock_get):
        mock_get.return_value = fake_response({"routes": [here_route(14_400)]})
        fetch_truck_routes(DALLAS, HOUSTON, DEPARTURE, load_weight_lb=0, via=(31.5, -96.2))
        self.assertEqual(mock_get.call_args.kwargs["params"]["via"], "31.5,-96.2!passThrough=true")

    @patch("planner.routing.requests.get")
    def test_route_is_named_after_its_longest_highways(self, mock_get):
        def numbers(*pairs):
            return [{"value": value, "routeType": route_type} for value, route_type in pairs]

        section = here_section(
            points=[(41.0, -88.0), (41.0, -95.0), (41.0, -100.0), (40.0, -104.0)],
            spans=[
                # I-80 shares pavement with US-6 here; only the interstate should count.
                {"offset": 0, "length": 600_000, "duration": 20_000, "routeNumbers": numbers(("US-6", 2), ("I-80", 1))},
                {"offset": 1, "length": 300_000, "duration": 10_000, "routeNumbers": numbers(("I-76", 1))},
                {"offset": 2, "length": 50_000, "duration": 2_000, "routeNumbers": numbers(("CO-2", 3))},
                {"offset": 3, "length": 10_000, "duration": 600},
            ],
            length_m=960_000, duration_s=32_600,
            departs="2026-11-02T08:00:00+00:00", arrives="2026-11-02T17:03:20+00:00",
        )
        mock_get.return_value = fake_response({"routes": [{"sections": [section]}]})
        route = fetch_truck_routes(DALLAS, HOUSTON, DEPARTURE, load_weight_lb=0)[0]
        self.assertEqual(route.highways, ("I-80", "I-76"))
        self.assertIn("routeNumbers", mock_get.call_args.kwargs["params"]["spans"])

    @patch("planner.routing.requests.get")
    def test_route_without_route_numbers_has_no_highways(self, mock_get):
        mock_get.return_value = fake_response({"routes": [here_route(14_400)]})
        self.assertEqual(fetch_truck_routes(DALLAS, HOUSTON, DEPARTURE, load_weight_lb=0)[0].highways, ())

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


def simple_route(duration_s, path):
    departs = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)
    return TruckRoute(
        path=path, stretches=[], distance_m=1000, duration_s=duration_s,
        departure_time=departs, arrival_time=departs,
    )


# A straight north-south road and a parallel one ~50 km east of it.
MAIN_ROAD = [(30 + i * 0.01, -96.0) for i in range(100)]
PARALLEL_ROAD = [(30 + i * 0.01, -95.5) for i in range(100)]
THIRD_ROAD = [(30 + i * 0.01, -95.0) for i in range(100)]


class DetourPointTests(SimpleTestCase):
    def test_point_is_beside_midpoint_of_north_bound_trip(self):
        south, north = Place("A", 30.0, -96.0), Place("B", 31.0, -96.0)
        left_lat, left_lng = _detour_point(south, north, 0.2)
        right_lat, right_lng = _detour_point(south, north, -0.2)
        # Travelling north, left is west and right is east; latitude stays at the midpoint.
        self.assertAlmostEqual(left_lat, 30.5)
        self.assertAlmostEqual(right_lat, 30.5)
        self.assertLess(left_lng, -96.0)
        self.assertGreater(right_lng, -96.0)

    def test_offset_is_same_ground_distance_as_fraction_of_trip(self):
        west, east = Place("A", 45.0, -100.0), Place("B", 45.0, -98.0)
        lat, lng = _detour_point(west, east, 0.2)
        # Trip runs east, so +0.2 is north; 2 deg lng at 45N ~= 1.414 deg lat of ground.
        self.assertAlmostEqual(lat - 45.0, 2 * cos(radians(45)) * 0.2)
        self.assertAlmostEqual(lng, -99.0)


class SameRoadTests(SimpleTestCase):
    def test_identical_and_parallel_roads(self):
        self.assertTrue(_mostly_same_road(simple_route(1, MAIN_ROAD), simple_route(1, MAIN_ROAD)))
        self.assertFalse(_mostly_same_road(simple_route(1, MAIN_ROAD), simple_route(1, PARALLEL_ROAD)))

    def test_out_and_back_spur_counts_as_same_road(self):
        spur = MAIN_ROAD[:50] + [(30.49, -96.0 + i * 0.01) for i in range(1, 5)] + MAIN_ROAD[50:]
        # Main road is fully contained in the spur route, so they're the same option.
        self.assertTrue(_mostly_same_road(simple_route(1, MAIN_ROAD), simple_route(1, spur)))


@patch("planner.routing.fetch_truck_routes")
class FetchRouteOptionsTests(SimpleTestCase):
    def test_no_detours_when_here_returns_three(self, mock_fetch):
        mock_fetch.return_value = [simple_route(100, MAIN_ROAD), simple_route(110, PARALLEL_ROAD),
                                   simple_route(120, THIRD_ROAD)]
        routes = fetch_route_options(DALLAS, HOUSTON, DEPARTURE, 0)
        self.assertEqual(len(routes), 3)
        self.assertEqual(mock_fetch.call_count, 1)

    def test_fills_gap_with_distinct_detour(self, mock_fetch):
        mock_fetch.side_effect = [
            [simple_route(100, MAIN_ROAD), simple_route(110, PARALLEL_ROAD)],
            [simple_route(150, THIRD_ROAD)],
        ]
        routes = fetch_route_options(DALLAS, HOUSTON, DEPARTURE, 0)
        self.assertEqual([r.duration_s for r in routes], [100, 110, 150])
        self.assertIsNone(routes[0].detour_via)
        self.assertIsNotNone(routes[2].detour_via)
        self.assertIn("via", mock_fetch.call_args.kwargs)

    def test_rejects_slow_duplicate_and_failed_detours(self, mock_fetch):
        mock_fetch.side_effect = [
            [simple_route(100, MAIN_ROAD)],
            [simple_route(201, PARALLEL_ROAD)],   # over 2x the fastest time
            [simple_route(120, MAIN_ROAD)],       # same road as the main route
            RoutingError("no route"),             # detour point unreachable
            [simple_route(150, THIRD_ROAD)],      # accepted
        ]
        routes = fetch_route_options(DALLAS, HOUSTON, DEPARTURE, 0)
        self.assertEqual([r.duration_s for r in routes], [100, 150])
        self.assertEqual(mock_fetch.call_count, 5)

    def test_initial_failure_is_not_swallowed(self, mock_fetch):
        mock_fetch.side_effect = RoutingError("HERE found no truck route")
        with self.assertRaises(RoutingError):
            fetch_route_options(DALLAS, HOUSTON, DEPARTURE, 0)
