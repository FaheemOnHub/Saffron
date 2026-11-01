"""
A grid of weather sample points covering the band of land around the routes.

The heatmap needs weather across the whole trip corridor, not just on the
roads. We lay a regular lat/lng grid over the routes and keep the points within
CORRIDOR_HALF_WIDTH_MILES of any route. Spacing grows with trip length so the
point count stays under MAX_GRID_POINTS (each point is one Open-Meteo call).
"""

from dataclasses import dataclass
from datetime import timedelta, timezone
from math import ceil, cos, radians, sqrt

from planner.checkpoints import METERS_PER_MILE, haversine_m
from planner.risk import (
    RAIN_SCORE_ANCHORS,
    SNOW_SCORE_ANCHORS,
    WIND_SCORE_ANCHORS,
    assess_checkpoint,
    condition_score,
)
from planner.weather import hourly_forecasts

CORRIDOR_HALF_WIDTH_MILES = 30
MAX_GRID_POINTS = 150
# Forecast models resolve roughly 3-10 km; a finer grid adds calls, not detail.
MIN_SPACING_MILES = 6
# Route points closer together than this add no accuracy to the distance check.
ROUTE_SAMPLE_SPACING_MILES = 3
SPACING_GROWTH = 1.15
# The slider covers departure hour 0 through hour 48.
FORECAST_HOUR_COUNT = 49

METERS_PER_DEGREE_LAT = 111_132


@dataclass(frozen=True)
class CorridorGrid:
    points: list  # [(lat, lng), ...]
    spacing_m: float


@dataclass(frozen=True)
class HeatmapFrame:
    """Values for every grid point at one hour; None where there's no forecast."""

    hour: object  # UTC datetime
    risk_levels: list  # official RiskLevel ints, with the load rules applied
    wind_scores: list  # 0-4 display scores, see risk.condition_score
    rain_scores: list
    snow_scores: list


@dataclass(frozen=True)
class CorridorForecast:
    grid: CorridorGrid
    frames: list  # HeatmapFrame per hour, departure hour first


def _sample_route_points(routes):
    """Every route's path thinned to one point per ROUTE_SAMPLE_SPACING_MILES."""
    every_m = ROUTE_SAMPLE_SPACING_MILES * METERS_PER_MILE
    samples = []
    for route in routes:
        last_kept = None
        for point in route.path:
            if last_kept is None or haversine_m(last_kept, point) >= every_m:
                samples.append(point)
                last_kept = point
        if route.path and route.path[-1] != last_kept:
            samples.append(route.path[-1])
    return samples


def _grid_within_corridor(samples, spacing_miles, reference_lat):
    """Grid points (anchored at a fixed origin) within the corridor of any sample."""
    lat_step = spacing_miles * METERS_PER_MILE / METERS_PER_DEGREE_LAT
    lng_step = lat_step / cos(radians(reference_lat))
    radius_m = CORRIDOR_HALF_WIDTH_MILES * METERS_PER_MILE
    reach = ceil(CORRIDOR_HALF_WIDTH_MILES / spacing_miles)

    kept = {}
    for sample_lat, sample_lng in samples:
        row_center, column_center = round(sample_lat / lat_step), round(sample_lng / lng_step)
        for row in range(row_center - reach, row_center + reach + 1):
            for column in range(column_center - reach, column_center + reach + 1):
                if (row, column) in kept:
                    continue
                grid_point = (row * lat_step, column * lng_step)
                if haversine_m(grid_point, (sample_lat, sample_lng)) <= radius_m:
                    kept[(row, column)] = grid_point
    # Sorted so the same routes always give the same point order.
    return [kept[key] for key in sorted(kept)]


def corridor_grid(routes):
    samples = _sample_route_points(routes)
    if not samples:
        return CorridorGrid(points=[], spacing_m=0.0)
    reference_lat = sum(lat for lat, _ in samples) / len(samples)

    # First guess: corridor area / point budget, using the sampled route length.
    route_miles = ROUTE_SAMPLE_SPACING_MILES * len(samples)
    corridor_area = route_miles * 2 * CORRIDOR_HALF_WIDTH_MILES
    spacing_miles = max(MIN_SPACING_MILES, sqrt(corridor_area / MAX_GRID_POINTS))

    points = _grid_within_corridor(samples, spacing_miles, reference_lat)
    while len(points) > MAX_GRID_POINTS:
        spacing_miles *= SPACING_GROWTH
        points = _grid_within_corridor(samples, spacing_miles, reference_lat)
    return CorridorGrid(points=points, spacing_m=spacing_miles * METERS_PER_MILE)



def _frame(hour, readings, load_weight_lb):
    def score(anchors, value_of):
        return [None if r is None else round(condition_score(value_of(r), anchors), 2) for r in readings]

    return HeatmapFrame(
        hour=hour,
        risk_levels=[
            None if r is None else int(assess_checkpoint(
                r.wind_mph, r.rain_in_per_hr, r.snow_in_per_hr, load_weight_lb,
            ).level)
            for r in readings
        ],
        wind_scores=score(WIND_SCORE_ANCHORS, lambda r: r.wind_mph),
        rain_scores=score(RAIN_SCORE_ANCHORS, lambda r: r.rain_in_per_hr),
        snow_scores=score(SNOW_SCORE_ANCHORS, lambda r: r.snow_in_per_hr),
    )


def corridor_forecast(routes, departure_time, load_weight_lb):
    """Hourly heatmap frames over the corridor, from the departure hour onward."""
    grid = corridor_grid(routes)
    # Floor in UTC: Open-Meteo's slots are whole UTC hours, and some zones are offset by :30.
    first_hour = departure_time.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hours = [first_hour + timedelta(hours=offset) for offset in range(FORECAST_HOUR_COUNT)]
    if not grid.points:
        return CorridorForecast(grid=grid, frames=[])

    per_point = hourly_forecasts(grid.points, first_hour, FORECAST_HOUR_COUNT)
    frames = [
        _frame(hour, [point_hours[offset] for point_hours in per_point], load_weight_lb)
        for offset, hour in enumerate(hours)
    ]
    return CorridorForecast(grid=grid, frames=frames)
