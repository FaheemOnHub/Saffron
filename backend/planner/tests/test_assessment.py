from datetime import datetime, timezone

from django.test import SimpleTestCase

from planner.assessment import assess_route, rank_routes, rate_checkpoints
from planner.checkpoints import Checkpoint
from planner.risk import RiskLevel
from planner.routing import TruckRoute
from planner.weather import WeatherReading

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = RiskLevel
WHEN = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)

# Weather that lands in each risk level for a light truck (rain-driven, calm wind).
RAIN_FOR_LEVEL = {LOW: 0.0, MODERATE: 0.15, HIGH: 0.3, SEVERE: 0.7, NO_TRAVEL: 1.5}


def reading(wind=5.0, gust=8.0, rain=0.0, snow=0.0):
    return WeatherReading(wind, gust, rain, snow, WHEN)


def checkpoint(coverage_miles, sequence=0):
    return Checkpoint(sequence, 0.0, 32.0, -96.0, WHEN, coverage_miles)


def route(duration_s=3600):
    return TruckRoute([], [], 1000, duration_s, WHEN, WHEN)


def assessed(segments, duration_s=3600, load_weight_lb=0):
    """Build an assessed route from (miles, risk level or None for no forecast) pairs."""
    checkpoints = [checkpoint(miles, i) for i, (miles, _) in enumerate(segments)]
    readings = [None if level is None else reading(rain=RAIN_FOR_LEVEL[level]) for _, level in segments]
    return assess_route(route(duration_s), rate_checkpoints(checkpoints, readings, load_weight_lb))


class RateCheckpointsTests(SimpleTestCase):
    def test_uses_risk_rules_including_load(self):
        rated = rate_checkpoints([checkpoint(10)], [reading(wind=40)], load_weight_lb=45_000)[0]
        self.assertEqual(rated.risk.level, SEVERE)
        self.assertTrue(rated.risk.raised_by_load)

    def test_missing_forecast_has_no_risk(self):
        rated = rate_checkpoints([checkpoint(10)], [None], load_weight_lb=0)[0]
        self.assertIsNone(rated.risk)
        self.assertFalse(rated.gust_warning)

    def test_gusts_warn_but_do_not_change_level(self):
        rated = rate_checkpoints([checkpoint(10)], [reading(wind=20, gust=38)], load_weight_lb=0)[0]
        self.assertEqual(rated.risk.level, LOW)
        self.assertTrue(rated.gust_warning)

    def test_no_gust_warning_below_threshold_or_when_wind_already_high(self):
        calm, already_high = rate_checkpoints(
            [checkpoint(10), checkpoint(10)], [reading(wind=20, gust=34), reading(wind=36, gust=50)], 0,
        )
        self.assertFalse(calm.gust_warning)
        self.assertFalse(already_high.gust_warning)

    def test_mismatched_lengths_are_rejected(self):
        with self.assertRaises(ValueError):
            rate_checkpoints([checkpoint(10)], [], 0)


class AssessRouteTests(SimpleTestCase):
    def test_miles_by_level_and_weighted_average(self):
        assessment = assessed([(5, LOW), (25, HIGH), (25, LOW), (5, SEVERE)])
        self.assertEqual(assessment.high_miles, 25)
        self.assertEqual(assessment.severe_miles, 5)
        self.assertEqual(assessment.miles_by_level[LOW], 30)
        # (0*30 + 2*25 + 3*5) / 60
        self.assertAlmostEqual(assessment.average_risk, 65 / 60)
        self.assertEqual(assessment.worst_level, SEVERE)

    def test_unknown_miles_are_counted_separately_and_left_out_of_average(self):
        assessment = assessed([(10, HIGH), (10, None)])
        self.assertEqual(assessment.unknown_miles, 10)
        self.assertEqual(assessment.average_risk, HIGH)

    def test_all_unknown_route(self):
        assessment = assessed([(10, None), (10, None)])
        self.assertIsNone(assessment.worst_level)
        self.assertEqual(assessment.average_risk, 0.0)

    def test_gust_warnings_are_counted(self):
        rated = rate_checkpoints(
            [checkpoint(10), checkpoint(10)], [reading(gust=40), reading(gust=10)], 0,
        )
        self.assertEqual(assess_route(route(), rated).gust_warning_count, 1)


class RankingPriorityTests(SimpleTestCase):
    """Each rule should only decide when every rule above it is tied."""

    def test_fewer_severe_miles_beats_fewer_high_miles_and_faster_time(self):
        some_severe = assessed([(10, SEVERE), (90, LOW)], duration_s=3600)
        lots_of_high = assessed([(80, HIGH), (20, LOW)], duration_s=9000)
        ranked = rank_routes([some_severe, lots_of_high])
        self.assertIs(ranked[0], lots_of_high)

    def test_fewer_high_miles_beats_lower_average_and_faster_time(self):
        # Same Severe miles; first route has fewer High but more Moderate (higher average).
        fewer_high = assessed([(10, HIGH), (90, MODERATE)], duration_s=9000)
        more_high = assessed([(20, HIGH), (80, LOW)], duration_s=3600)
        self.assertGreater(fewer_high.average_risk, more_high.average_risk)
        self.assertIs(rank_routes([more_high, fewer_high])[0], fewer_high)

    def test_lower_average_beats_faster_time(self):
        calmer = assessed([(100, LOW)], duration_s=9000)
        breezier = assessed([(100, MODERATE)], duration_s=3600)
        self.assertIs(rank_routes([breezier, calmer])[0], calmer)

    def test_travel_time_breaks_full_weather_tie(self):
        slow = assessed([(100, LOW)], duration_s=9000)
        fast = assessed([(100, LOW)], duration_s=3600)
        self.assertIs(rank_routes([slow, fast])[0], fast)

    def test_any_no_travel_miles_rank_last(self):
        blocked = assessed([(5, NO_TRAVEL), (95, LOW)], duration_s=3600)
        stormy = assessed([(60, SEVERE), (40, HIGH)], duration_s=9000)
        self.assertIs(rank_routes([blocked, stormy])[-1], blocked)

    def test_tiny_float_differences_do_not_override_travel_time(self):
        nearly_same = assessed([(100.0001, LOW), (10, HIGH)], duration_s=9000)
        faster = assessed([(100, LOW), (10.00001, HIGH)], duration_s=3600)
        self.assertIs(rank_routes([nearly_same, faster])[0], faster)


class RankingOutputTests(SimpleTestCase):
    def test_ranks_numbered_and_only_first_recommended(self):
        ranked = rank_routes([assessed([(100, HIGH)]), assessed([(100, LOW)]), assessed([(100, MODERATE)])])
        self.assertEqual([a.rank for a in ranked], [1, 2, 3])
        self.assertEqual([a.is_recommended for a in ranked], [True, False, False])
        self.assertEqual([a.worst_level for a in ranked], [LOW, MODERATE, HIGH])

    def test_reason_names_deciding_rule_with_values(self):
        ranked = rank_routes([assessed([(30, SEVERE), (70, LOW)]), assessed([(12.5, SEVERE), (87.5, LOW)])])
        self.assertEqual(ranked[0].recommendation_reason, "Fewest Severe miles (12.5 mi vs 30 mi).")

    def test_reason_for_average_risk(self):
        ranked = rank_routes([assessed([(100, MODERATE)]), assessed([(100, LOW)])])
        self.assertEqual(ranked[0].recommendation_reason, "Lowest average risk (0.00 vs 1.00).")

    def test_reason_for_travel_time(self):
        ranked = rank_routes([assessed([(100, LOW)], duration_s=5400), assessed([(100, LOW)], duration_s=3660)])
        self.assertEqual(
            ranked[0].recommendation_reason,
            "Same weather risk as the next option, and fastest (1h 01m vs 1h 30m).",
        )

    def test_single_route_and_empty_list(self):
        only = rank_routes([assessed([(100, LOW)])])
        self.assertEqual(only[0].recommendation_reason, "Only route available.")
        self.assertEqual(rank_routes([]), [])
