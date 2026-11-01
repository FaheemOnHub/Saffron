"""
Rate each route's weather risk and rank the routes.

Ranking follows the assignment's priorities, in order:
  1. fewest Severe miles
  2. fewest High miles
  3. lowest average risk
  4. shortest travel time
Ahead of all four, any No Travel miles push a route down, so a route the
truck can't legally drive is never recommended over one it can.
"""

from dataclasses import dataclass

from planner.risk import RiskLevel, assess_checkpoint

# Sustained wind sets the risk level. Gusts only raise a warning, shown when
# they reach the High wind band while sustained wind is still below it.
GUST_WARNING_MPH = 35

# Miles and averages are estimates from sampled checkpoints, so differences
# smaller than these are noise and shouldn't decide the ranking.
MILES_PRECISION = 1
AVERAGE_RISK_PRECISION = 2


@dataclass(frozen=True)
class RatedCheckpoint:
    checkpoint: object  # checkpoints.Checkpoint
    weather: object  # weather.WeatherReading, or None when no forecast exists
    risk: object  # risk.CheckpointRisk, or None when no forecast exists
    gust_warning: bool


@dataclass
class RouteAssessment:
    route: object  # routing.TruckRoute
    checkpoints: list
    miles_by_level: dict  # RiskLevel -> miles
    unknown_miles: float
    average_risk: float  # mileage-weighted, 0 (Low) to 4 (No Travel)
    worst_level: object  # RiskLevel, or None if no checkpoint had a forecast
    gust_warning_count: int
    # Filled in by rank_routes.
    rank: int = 0
    is_recommended: bool = False
    recommendation_reason: str = ""

    @property
    def severe_miles(self):
        return self.miles_by_level[RiskLevel.SEVERE]

    @property
    def high_miles(self):
        return self.miles_by_level[RiskLevel.HIGH]

    @property
    def no_travel_miles(self):
        return self.miles_by_level[RiskLevel.NO_TRAVEL]


def rate_checkpoints(checkpoints, readings, load_weight_lb):
    """Pair each checkpoint with its forecast and risk. `readings` is in checkpoint order."""
    if len(checkpoints) != len(readings):
        raise ValueError("Each checkpoint needs exactly one weather reading (or None).")
    rated = []
    for checkpoint, reading in zip(checkpoints, readings):
        if reading is None:
            rated.append(RatedCheckpoint(checkpoint, None, None, gust_warning=False))
            continue
        risk = assess_checkpoint(
            wind_mph=reading.wind_mph,
            rain_in_per_hr=reading.rain_in_per_hr,
            snow_in_per_hr=reading.snow_in_per_hr,
            load_weight_lb=load_weight_lb,
        )
        gust_warning = reading.wind_gust_mph >= GUST_WARNING_MPH and risk.wind_level < RiskLevel.HIGH
        rated.append(RatedCheckpoint(checkpoint, reading, risk, gust_warning))
    return rated


def assess_route(route, rated_checkpoints):
    miles_by_level = {level: 0.0 for level in RiskLevel}
    unknown_miles = 0.0
    weighted_risk_total = 0.0
    for rated in rated_checkpoints:
        miles = rated.checkpoint.coverage_miles
        if rated.risk is None:
            unknown_miles += miles
            continue
        miles_by_level[rated.risk.level] += miles
        weighted_risk_total += rated.risk.level * miles

    known_miles = sum(miles_by_level.values())
    known_levels = [rated.risk.level for rated in rated_checkpoints if rated.risk is not None]
    return RouteAssessment(
        route=route,
        checkpoints=rated_checkpoints,
        miles_by_level=miles_by_level,
        unknown_miles=unknown_miles,
        # Weighted by miles so the short origin/destination checkpoints count less.
        average_risk=weighted_risk_total / known_miles if known_miles else 0.0,
        worst_level=max(known_levels) if known_levels else None,
        gust_warning_count=sum(rated.gust_warning for rated in rated_checkpoints),
    )


# (label, value getter, unit) in priority order. Shared by the sort key and the
# explanation, so the reason shown to the driver always matches the real ranking.
RANKING_CRITERIA = (
    ("No Travel miles", lambda a: round(a.no_travel_miles, MILES_PRECISION), "mi"),
    ("Severe miles", lambda a: round(a.severe_miles, MILES_PRECISION), "mi"),
    ("High miles", lambda a: round(a.high_miles, MILES_PRECISION), "mi"),
    ("average risk", lambda a: round(a.average_risk, AVERAGE_RISK_PRECISION), ""),
    ("travel time", lambda a: a.route.duration_s, "s"),
)


def _ranking_key(assessment):
    return tuple(value_of(assessment) for _, value_of, _ in RANKING_CRITERIA)


def _format_value(value, unit):
    if unit == "s":
        hours, minutes = divmod(round(value / 60), 60)
        return f"{hours}h {minutes:02d}m"
    if unit == "mi":
        return f"{value:g} mi"
    return f"{value:.2f}"


def _explain(winner, runner_up):
    """Name the first criterion where the winner beats the runner-up."""
    for label, value_of, unit in RANKING_CRITERIA:
        best, next_best = value_of(winner), value_of(runner_up)
        if best == next_best:
            continue
        comparison = f"({_format_value(best, unit)} vs {_format_value(next_best, unit)})"
        if unit == "s":
            return f"Same weather risk as the next option, and fastest {comparison}."
        if label == "average risk":
            return f"Lowest average risk {comparison}."
        return f"Fewest {label} {comparison}."
    return "Ties with the next route on every criterion."


def rank_routes(assessments):
    """Sort best first, number them, and mark the recommendation with its reason."""
    ranked = sorted(assessments, key=_ranking_key)
    for position, assessment in enumerate(ranked, start=1):
        assessment.rank = position
        assessment.is_recommended = position == 1
    if len(ranked) == 1:
        ranked[0].recommendation_reason = "Only route available."
    elif ranked:
        ranked[0].recommendation_reason = _explain(ranked[0], ranked[1])
    return ranked
