"""
Place weather checkpoints along a route and work out when the truck reaches each one.

Arrival times come from HERE's per-stretch drive times, not an average speed,
so a checkpoint past a slow city section gets a later ETA than one the same
distance down an open interstate.
"""

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt

from planner.routing import RouteStretch
from planner.timezones import timezone_name_at

METERS_PER_MILE = 1609.344
EARTH_RADIUS_M = 6_371_000
CHECKPOINT_INTERVAL_OPTIONS_MILES = (10, 25, 50)
# A scheduled checkpoint this close to the destination would duplicate it.
MIN_GAP_BEFORE_DESTINATION_MILES = 1.0


@dataclass(frozen=True)
class Checkpoint:
    sequence: int
    distance_miles: float  # along the route from the origin
    latitude: float
    longitude: float
    eta: datetime
    # Miles of road this checkpoint's weather stands for: halfway back to the
    # previous checkpoint and halfway on to the next. These add up to the route length.
    coverage_miles: float
    timezone: str = "UTC"  # local zone at this point, for showing its ETA


def haversine_m(point_a, point_b):
    lat_a, lng_a = map(radians, point_a)
    lat_b, lng_b = map(radians, point_b)
    a = sin((lat_b - lat_a) / 2) ** 2 + cos(lat_a) * cos(lat_b) * sin((lng_b - lng_a) / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


def _progress_along_path(route):
    """Distance (m) and drive time (s) from the origin to every point on the path.

    Inside each stretch, HERE's length and time are spread over the points in
    proportion to the ground distance between them. Using HERE's length (not
    our own haversine sum) keeps mileage consistent with the route summary.
    """
    stretches = route.stretches or [RouteStretch(0, route.distance_m, route.duration_s)]
    last_index = len(route.path) - 1
    distances_m = [0.0] * len(route.path)
    durations_s = [0.0] * len(route.path)
    distance_so_far, duration_so_far = 0.0, 0.0

    for position, stretch in enumerate(stretches):
        start = stretch.start_point_index
        end = stretches[position + 1].start_point_index if position + 1 < len(stretches) else last_index
        step_lengths = [haversine_m(route.path[i], route.path[i + 1]) for i in range(start, end)]
        ground_length = sum(step_lengths)
        walked = 0.0
        for offset, step in enumerate(step_lengths, start=1):
            walked += step
            share = walked / ground_length if ground_length else 1.0
            distances_m[start + offset] = distance_so_far + share * stretch.length_m
            durations_s[start + offset] = duration_so_far + share * stretch.duration_s
        distance_so_far += stretch.length_m
        duration_so_far += stretch.duration_s

    return distances_m, durations_s


def _locate(target_m, path, distances_m, durations_s):
    """Interpolated (lat, lng, seconds from departure) at a distance along the route."""
    index = bisect_left(distances_m, target_m)
    if index == 0:
        return (*path[0], durations_s[0])
    if index >= len(path):
        return (*path[-1], durations_s[-1])
    before, after = index - 1, index
    gap = distances_m[after] - distances_m[before]
    share = (target_m - distances_m[before]) / gap if gap else 0.0

    def blend(start_value, end_value):
        return start_value + share * (end_value - start_value)

    return (
        blend(path[before][0], path[after][0]),
        blend(path[before][1], path[after][1]),
        blend(durations_s[before], durations_s[after]),
    )


def place_checkpoints(route, interval_miles):
    """Checkpoints at the origin, every `interval_miles`, and the destination."""
    if interval_miles not in CHECKPOINT_INTERVAL_OPTIONS_MILES:
        raise ValueError(f"Checkpoint interval must be one of {CHECKPOINT_INTERVAL_OPTIONS_MILES} miles.")
    if len(route.path) < 2:
        raise ValueError("Route path needs at least two points.")

    distances_m, durations_s = _progress_along_path(route)
    total_m = distances_m[-1]
    interval_m = interval_miles * METERS_PER_MILE

    last_scheduled_m = total_m - MIN_GAP_BEFORE_DESTINATION_MILES * METERS_PER_MILE
    targets_m = [0.0]
    next_target = interval_m
    while next_target < last_scheduled_m:
        targets_m.append(next_target)
        next_target += interval_m
    if total_m > 0:
        targets_m.append(total_m)

    checkpoints = []
    for sequence, target_m in enumerate(targets_m):
        latitude, longitude, seconds_from_departure = _locate(target_m, route.path, distances_m, durations_s)
        previous_m = targets_m[sequence - 1] if sequence > 0 else target_m
        following_m = targets_m[sequence + 1] if sequence + 1 < len(targets_m) else target_m
        checkpoints.append(
            Checkpoint(
                sequence=sequence,
                distance_miles=target_m / METERS_PER_MILE,
                latitude=latitude,
                longitude=longitude,
                eta=route.departure_time + timedelta(seconds=seconds_from_departure),
                coverage_miles=(following_m - previous_m) / 2 / METERS_PER_MILE,
                timezone=timezone_name_at(latitude, longitude),
            )
        )
    return checkpoints
