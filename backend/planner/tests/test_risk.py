from django.test import SimpleTestCase

from planner.risk import (
    RAIN_SCORE_ANCHORS,
    SNOW_SCORE_ANCHORS,
    WIND_SCORE_ANCHORS,
    RiskLevel,
    apply_load_rules,
    assess_checkpoint,
    classify_rain,
    classify_snow,
    classify_wind,
    condition_score,
)

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = RiskLevel


class WindClassificationTests(SimpleTestCase):
    def test_each_band_including_boundaries(self):
        cases = [
            (0, LOW), (24.9, LOW),
            (25, MODERATE), (34.9, MODERATE),
            (35, HIGH), (44.9, HIGH),
            (45, SEVERE), (54.9, SEVERE),
            (55, NO_TRAVEL), (80, NO_TRAVEL),
        ]
        for wind_mph, expected in cases:
            with self.subTest(wind_mph=wind_mph):
                self.assertEqual(classify_wind(wind_mph), expected)


class RainClassificationTests(SimpleTestCase):
    def test_each_band_including_boundaries(self):
        cases = [
            (0, LOW), (0.09, LOW),
            (0.10, MODERATE), (0.24, MODERATE),
            (0.25, HIGH), (0.49, HIGH),
            (0.50, SEVERE), (1.00, SEVERE),
            (1.01, NO_TRAVEL),
        ]
        for rain, expected in cases:
            with self.subTest(rain=rain):
                self.assertEqual(classify_rain(rain), expected)


class SnowClassificationTests(SimpleTestCase):
    def test_each_band_including_boundaries(self):
        cases = [
            (0, LOW), (0.49, LOW),
            (0.5, MODERATE), (0.99, MODERATE),
            (1.0, HIGH), (1.99, HIGH),
            (2.0, SEVERE), (3.0, SEVERE),
            (3.01, NO_TRAVEL),
        ]
        for snow, expected in cases:
            with self.subTest(snow=snow):
                self.assertEqual(classify_snow(snow), expected)


class NegativeReadingTests(SimpleTestCase):
    def test_negative_values_are_rejected(self):
        for classify in (classify_wind, classify_rain, classify_snow):
            with self.subTest(classify=classify.__name__):
                with self.assertRaises(ValueError):
                    classify(-1)
        with self.assertRaises(ValueError):
            apply_load_rules(LOW, -500)


class LoadRuleTests(SimpleTestCase):
    def test_severe_wind_with_heavy_load_is_no_travel(self):
        self.assertEqual(apply_load_rules(SEVERE, 30_001), NO_TRAVEL)

    def test_severe_wind_at_exactly_30000_lb_stays_severe(self):
        self.assertEqual(apply_load_rules(SEVERE, 30_000), SEVERE)

    def test_high_wind_with_heavy_load_is_severe(self):
        self.assertEqual(apply_load_rules(HIGH, 40_001), SEVERE)

    def test_high_wind_at_exactly_40000_lb_stays_high(self):
        self.assertEqual(apply_load_rules(HIGH, 40_000), HIGH)

    def test_heavy_load_does_not_change_calm_wind(self):
        for level in (LOW, MODERATE):
            with self.subTest(level=level):
                self.assertEqual(apply_load_rules(level, 80_000), level)

    def test_no_travel_wind_is_no_travel_for_empty_truck(self):
        self.assertEqual(assess_checkpoint(55, 0, 0, 0).level, NO_TRAVEL)


class AssessCheckpointTests(SimpleTestCase):
    def test_overall_level_is_worst_condition(self):
        risk = assess_checkpoint(wind_mph=10, rain_in_per_hr=0.3, snow_in_per_hr=0.6, load_weight_lb=20_000)
        self.assertEqual(risk.level, HIGH)
        self.assertEqual(risk.rain_level, HIGH)
        self.assertEqual(risk.snow_level, MODERATE)
        self.assertFalse(risk.raised_by_load)

    def test_load_rule_can_drive_overall_level(self):
        risk = assess_checkpoint(wind_mph=40, rain_in_per_hr=0, snow_in_per_hr=0, load_weight_lb=45_000)
        self.assertEqual(risk.level, SEVERE)
        self.assertTrue(risk.raised_by_load)

    def test_heavy_load_in_45_mph_wind_is_no_travel(self):
        risk = assess_checkpoint(wind_mph=45, rain_in_per_hr=0, snow_in_per_hr=0, load_weight_lb=35_000)
        self.assertEqual(risk.level, NO_TRAVEL)

    def test_label_is_human_readable(self):
        self.assertEqual(NO_TRAVEL.label, "No Travel")


class ConditionScoreTests(SimpleTestCase):
    def test_band_floors_score_whole_levels(self):
        self.assertEqual([condition_score(v, WIND_SCORE_ANCHORS) for v in (0, 25, 35, 45, 55)], [0, 1, 2, 3, 4])
        self.assertEqual([condition_score(v, RAIN_SCORE_ANCHORS) for v in (0, 0.10, 0.25, 0.50, 1.00)], [0, 1, 2, 3, 4])
        self.assertEqual([condition_score(v, SNOW_SCORE_ANCHORS) for v in (0, 0.5, 1.0, 2.0, 3.0)], [0, 1, 2, 3, 4])

    def test_between_floors_interpolates_and_caps(self):
        self.assertAlmostEqual(condition_score(30, WIND_SCORE_ANCHORS), 1.5)
        self.assertAlmostEqual(condition_score(0.75, RAIN_SCORE_ANCHORS), 3.5)
        self.assertEqual(condition_score(90, WIND_SCORE_ANCHORS), 4.0)
        self.assertEqual(condition_score(-1, WIND_SCORE_ANCHORS), 0.0)
