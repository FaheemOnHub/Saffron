from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from planner.checkpoints import METERS_PER_MILE, haversine_m, place_checkpoints
from planner.routing import RouteStretch, TruckRoute

DEPARTURE = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)


def north_bound_path(miles, step_miles=1):
    """Points due north along a meridian, one every `step_miles`."""
    degrees_per_mile = METERS_PER_MILE / haversine_m((0, 0), (1, 0))
    return [(30 + i * step_miles * degrees_per_mile, -96.0) for i in range(int(miles / step_miles) + 1)]


def make_route(path, stretches, distance_m, duration_s):
    return TruckRoute(
        path=path, stretches=stretches, distance_m=distance_m, duration_s=duration_s,
        departure_time=DEPARTURE, arrival_time=DEPARTURE + timedelta(seconds=duration_s),
    )


def even_route(miles, hours):
    meters = miles * METERS_PER_MILE
    return make_route(north_bound_path(miles), [RouteStretch(0, meters, hours * 3600)], meters, hours * 3600)


class HaversineTests(SimpleTestCase):
    def test_one_degree_of_latitude(self):
        self.assertAlmostEqual(haversine_m((0, 0), (1, 0)) / 1000, 111.19, places=1)


class CheckpointSpacingTests(SimpleTestCase):
    def test_origin_every_interval_and_destination(self):
        checkpoints = place_checkpoints(even_route(miles=60, hours=1), interval_miles=25)
        self.assertEqual([round(c.distance_miles, 3) for c in checkpoints], [0, 25, 50, 60])
        self.assertEqual([c.sequence for c in checkpoints], [0, 1, 2, 3])

    def test_no_duplicate_when_route_ends_on_an_interval(self):
        checkpoints = place_checkpoints(even_route(miles=50, hours=1), interval_miles=25)
        self.assertEqual([round(c.distance_miles, 3) for c in checkpoints], [0, 25, 50])

    def test_checkpoint_just_before_destination_is_skipped(self):
        checkpoints = place_checkpoints(even_route(miles=50.5, hours=1), interval_miles=25)
        self.assertEqual([round(c.distance_miles, 3) for c in checkpoints], [0, 25, 50.5])

    def test_zero_length_route_has_single_checkpoint(self):
        route = make_route([(30.0, -96.0), (30.0, -96.0)], [RouteStretch(0, 0, 0)], 0, 0)
        checkpoints = place_checkpoints(route, interval_miles=10)
        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0].coverage_miles, 0)

    def test_coverage_adds_up_to_route_length(self):
        for interval in (10, 25, 50):
            with self.subTest(interval=interval):
                checkpoints = place_checkpoints(even_route(miles=137, hours=2), interval)
                self.assertAlmostEqual(sum(c.coverage_miles for c in checkpoints), 137, places=6)

    def test_coverage_is_half_gap_on_each_side(self):
        checkpoints = place_checkpoints(even_route(miles=60, hours=1), interval_miles=25)
        self.assertEqual([round(c.coverage_miles, 3) for c in checkpoints], [12.5, 25, 17.5, 5])

    def test_route_shorter_than_interval_gets_origin_and_destination(self):
        checkpoints = place_checkpoints(even_route(miles=8, hours=0.2), interval_miles=10)
        self.assertEqual(len(checkpoints), 2)
        self.assertAlmostEqual(checkpoints[-1].distance_miles, 8)

    def test_checkpoint_position_is_interpolated_between_points(self):
        meters = 20 * METERS_PER_MILE
        route = make_route(north_bound_path(20, step_miles=4), [RouteStretch(0, meters, 1200)], meters, 1200)
        checkpoint = place_checkpoints(route, interval_miles=10)[1]
        expected = north_bound_path(10)[-1]
        self.assertAlmostEqual(checkpoint.latitude, expected[0], places=6)
        self.assertAlmostEqual(checkpoint.longitude, expected[1], places=6)


class CheckpointEtaTests(SimpleTestCase):
    def test_even_speed_gives_proportional_eta(self):
        checkpoints = place_checkpoints(even_route(miles=100, hours=2), interval_miles=25)
        self.assertEqual(checkpoints[0].eta, DEPARTURE)
        self.assertEqual(checkpoints[2].eta, DEPARTURE + timedelta(hours=1))
        self.assertEqual(checkpoints[-1].eta, DEPARTURE + timedelta(hours=2))

    def test_slow_stretch_delays_later_checkpoints(self):
        # First 50 miles crawl through traffic (2 h), last 50 miles are open road (45 min).
        half = 50 * METERS_PER_MILE
        path = north_bound_path(100)
        route = make_route(path, [RouteStretch(0, half, 7200), RouteStretch(50, half, 2700)], 2 * half, 9900)
        checkpoints = place_checkpoints(route, interval_miles=25)
        self.assertEqual(checkpoints[1].eta, DEPARTURE + timedelta(hours=1))
        self.assertEqual(checkpoints[2].eta, DEPARTURE + timedelta(hours=2))
        self.assertEqual(checkpoints[3].eta, DEPARTURE + timedelta(hours=2, minutes=22, seconds=30))
        self.assertEqual(checkpoints[4].eta, DEPARTURE + timedelta(seconds=9900))

    def test_mileage_follows_here_length_not_straight_line(self):
        # HERE says the road is 10% longer than our straight-line points (curves we don't see).
        ground_m = 50 * METERS_PER_MILE
        route = make_route(north_bound_path(50), [RouteStretch(0, ground_m * 1.1, 3600)], ground_m * 1.1, 3600)
        checkpoints = place_checkpoints(route, interval_miles=25)
        self.assertAlmostEqual(checkpoints[-1].distance_miles, 55)
        self.assertEqual(len(checkpoints), 4)  # 0, 25, 50, 55

    def test_repeated_point_where_sections_join_is_harmless(self):
        path = north_bound_path(20)
        joined = path[:11] + path[10:]  # point 10 appears twice, like a HERE section boundary
        meters = 20 * METERS_PER_MILE
        stretches = [RouteStretch(0, meters / 2, 600), RouteStretch(11, meters / 2, 600)]
        checkpoints = place_checkpoints(make_route(joined, stretches, meters, 1200), interval_miles=10)
        self.assertEqual([c.eta - DEPARTURE for c in checkpoints],
                         [timedelta(0), timedelta(minutes=10), timedelta(minutes=20)])


class CheckpointValidationTests(SimpleTestCase):
    def test_unsupported_interval_is_rejected(self):
        with self.assertRaises(ValueError):
            place_checkpoints(even_route(miles=60, hours=1), interval_miles=30)

    def test_route_without_stretches_falls_back_to_route_totals(self):
        meters = 40 * METERS_PER_MILE
        route = make_route(north_bound_path(40), [], meters, 2400)
        checkpoints = place_checkpoints(route, interval_miles=10)
        self.assertEqual(checkpoints[2].eta, DEPARTURE + timedelta(minutes=20))
