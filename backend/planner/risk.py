"""
Weather risk rules for a single route checkpoint.

Thresholds come straight from the assignment's risk table. Where the table's
ranges touch (e.g. rain 0.25 is listed under both Moderate and High), a value
sitting exactly on a boundary is placed in the higher level. The one exception
is the rain/snow "No Travel" column, which the table writes as strictly greater
than (>1.00, >3.0), so 1.00 in/hr rain and 3.0 in/hr snow stay Severe.
"""

from bisect import bisect_right
from dataclasses import dataclass
from enum import IntEnum


class RiskLevel(IntEnum):
    # Integer values let us take max() across conditions and average along a route.
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self):
        return self.name.replace("_", " ").title()


# Lower bound (inclusive) of Moderate, High, Severe, and No Travel.
WIND_LEVEL_FLOORS_MPH = (25, 35, 45, 55)

# Lower bound (inclusive) of Moderate, High, Severe. No Travel is checked separately.
RAIN_LEVEL_FLOORS_IN_PER_HR = (0.10, 0.25, 0.50)
RAIN_NO_TRAVEL_ABOVE_IN_PER_HR = 1.00

SNOW_LEVEL_FLOORS_IN_PER_HR = (0.5, 1.0, 2.0)
SNOW_NO_TRAVEL_ABOVE_IN_PER_HR = 3.0

# Load rules: heavy trucks get pushed up a level in strong wind.
NO_TRAVEL_LOAD_IN_SEVERE_WIND_LB = 30_000
SEVERE_LOAD_IN_HIGH_WIND_LB = 40_000


@dataclass(frozen=True)
class CheckpointRisk:
    level: RiskLevel
    wind_level: RiskLevel
    rain_level: RiskLevel
    snow_level: RiskLevel
    raised_by_load: bool


def _level_from_floors(reading, level_floors, no_travel_above=None):
    if reading < 0:
        raise ValueError(f"Weather reading cannot be negative: {reading}")
    if no_travel_above is not None and reading > no_travel_above:
        return RiskLevel.NO_TRAVEL
    # bisect_right counts how many floors the reading has reached, which is the level.
    return RiskLevel(bisect_right(level_floors, reading))


def classify_wind(wind_mph):
    return _level_from_floors(wind_mph, WIND_LEVEL_FLOORS_MPH)


def classify_rain(rain_in_per_hr):
    return _level_from_floors(
        rain_in_per_hr, RAIN_LEVEL_FLOORS_IN_PER_HR, RAIN_NO_TRAVEL_ABOVE_IN_PER_HR
    )


def classify_snow(snow_in_per_hr):
    return _level_from_floors(
        snow_in_per_hr, SNOW_LEVEL_FLOORS_IN_PER_HR, SNOW_NO_TRAVEL_ABOVE_IN_PER_HR
    )


def apply_load_rules(wind_level, load_weight_lb):
    """Raise the wind level for heavy loads. Never lowers it."""
    if load_weight_lb < 0:
        raise ValueError(f"Load weight cannot be negative: {load_weight_lb}")
    # Wind >= 55 mph is already No Travel via the wind table, for any load.
    if wind_level == RiskLevel.SEVERE and load_weight_lb > NO_TRAVEL_LOAD_IN_SEVERE_WIND_LB:
        return RiskLevel.NO_TRAVEL
    if wind_level == RiskLevel.HIGH and load_weight_lb > SEVERE_LOAD_IN_HIGH_WIND_LB:
        return RiskLevel.SEVERE
    return wind_level


def assess_checkpoint(wind_mph, rain_in_per_hr, snow_in_per_hr, load_weight_lb):
    """Overall checkpoint risk is the worst of wind (after load rules), rain, and snow."""
    base_wind_level = classify_wind(wind_mph)
    wind_level = apply_load_rules(base_wind_level, load_weight_lb)
    rain_level = classify_rain(rain_in_per_hr)
    snow_level = classify_snow(snow_in_per_hr)
    return CheckpointRisk(
        level=max(wind_level, rain_level, snow_level),
        wind_level=wind_level,
        rain_level=rain_level,
        snow_level=snow_level,
        raised_by_load=wind_level != base_wind_level,
    )


# Continuous 0-4 scores for the heatmap only (never used for ranking).
# Each condition's band floors map to whole levels and values in between are
# interpolated, so wind, rain, and snow share one color scale with risk levels.
WIND_SCORE_ANCHORS = (0, *WIND_LEVEL_FLOORS_MPH)
RAIN_SCORE_ANCHORS = (0, *RAIN_LEVEL_FLOORS_IN_PER_HR, RAIN_NO_TRAVEL_ABOVE_IN_PER_HR)
SNOW_SCORE_ANCHORS = (0, *SNOW_LEVEL_FLOORS_IN_PER_HR, SNOW_NO_TRAVEL_ABOVE_IN_PER_HR)


def condition_score(reading, anchors):
    """Map a reading onto 0-4: anchors[i] scores i, linear between, capped at 4."""
    if reading <= 0:
        return 0.0
    for level in range(1, len(anchors)):
        if reading < anchors[level]:
            lower, upper = anchors[level - 1], anchors[level]
            return level - 1 + (reading - lower) / (upper - lower)
    return float(len(anchors) - 1)
