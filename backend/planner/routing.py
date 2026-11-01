"""
Geocoding and truck routing through the HERE APIs.

Everything HERE-specific (URLs, parameter names, response shape, the
flexible polyline format) stays in this module, so the rest of the planner
works with plain Place / TruckRoute objects.
"""

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from math import cos, radians

import flexpolyline
import requests
from django.conf import settings

HERE_GEOCODE_URL = "https://geocode.search.hereapi.com/v1/geocode"
HERE_ROUTES_URL = "https://router.hereapi.com/v8/routes"
REQUEST_TIMEOUT_SECONDS = 20

# HERE can return up to 6 alternatives; 2 alternatives + the main route = 3 options.
ALTERNATIVE_ROUTE_COUNT = 2
TARGET_ROUTE_COUNT = 3

# When HERE has fewer than 3 routes, we force detours through points beside the
# trip's midpoint. Offsets are a fraction of the straight-line trip length;
# positive is left of the direction of travel, negative is right.
DETOUR_OFFSET_FRACTIONS = (0.2, -0.2, 0.35, -0.35)
# A slow detour is still worth showing: it's the escape route when weather
# blocks the main highway, and the recommendation ranks it last otherwise.
# Beyond 2x the fastest time it stops being a realistic option.
MAX_DETOUR_DURATION_RATIO = 2.0
# Two routes count as the same road if this share of the shorter one overlaps.
# Overlap is measured on a ~1 km grid (2 decimal places of lat/lng).
SAME_ROAD_OVERLAP_RATIO = 0.9
ROAD_GRID_DECIMALS = 2
# A route is named after the highways it spends the most miles on.
HIGHWAY_NAME_COUNT = 2

KG_PER_LB = 0.45359237
# The driver enters cargo weight, but truck routing needs gross weight.
# A typical empty tractor + 53 ft trailer weighs about 35,000 lb.
EMPTY_TRUCK_WEIGHT_LB = 35_000


class RoutingError(Exception):
    """A place can't be found, no route exists, or the HERE API failed."""


class PlaceNotFoundError(RoutingError):
    """The geocoder had no match for what the driver typed."""


class NoRouteError(RoutingError):
    """Both places exist but HERE has no truck route between them."""


@dataclass(frozen=True)
class Place:
    label: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class RouteStretch:
    """A run of road where HERE reports one length and one drive time."""

    start_point_index: int
    length_m: float
    duration_s: float


@dataclass(frozen=True)
class TruckRoute:
    path: list  # [(lat, lng), ...] along the whole route
    stretches: list  # RouteStretch items covering the path in order
    distance_m: float
    duration_s: float
    departure_time: datetime
    arrival_time: datetime
    # Set when we forced this route through a detour point; None for HERE's own routes.
    detour_via: tuple = None
    # Main highways by miles driven, e.g. ("I-80", "I-76"); empty when HERE has none.
    highways: tuple = ()


def _call_here(url, params):
    if not settings.HERE_API_KEY:
        raise RoutingError("HERE_API_KEY is not configured.")
    params = {**params, "apiKey": settings.HERE_API_KEY}
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as error:
        raise RoutingError(f"Could not reach HERE: {error}") from error
    if not response.ok:
        # Routing/geocoding errors use "title"; auth errors use "error_description".
        try:
            error_body = response.json()
            detail = error_body.get("title") or error_body.get("error_description") or response.text
        except ValueError:
            detail = response.text
        raise RoutingError(f"HERE request failed ({response.status_code}): {detail}")
    return response.json()


def geocode_place(query):
    query = (query or "").strip()
    if not query:
        raise PlaceNotFoundError("Place name is empty.")
    data = _call_here(HERE_GEOCODE_URL, {"q": query, "limit": 1})
    items = data.get("items") or []
    if not items:
        raise PlaceNotFoundError(f"Could not find a location for '{query}'.")
    best_match = items[0]
    return Place(
        label=best_match.get("title", query),
        latitude=best_match["position"]["lat"],
        longitude=best_match["position"]["lng"],
    )


def gross_weight_kg(load_weight_lb):
    return round((EMPTY_TRUCK_WEIGHT_LB + load_weight_lb) * KG_PER_LB)


def _main_highway(span):
    """The span's most important route number (lowest HERE routeType), if any.

    Roads often carry several numbers at once (I-80 shares pavement with US-6);
    counting only the top-class one keeps a route from being named twice.
    """
    numbers = span.get("routeNumbers") or []
    if not numbers:
        return None
    return min(numbers, key=lambda number: number.get("routeType", 99))["value"]


def _parse_route(route_data):
    """Join a HERE route's sections into one continuous path with stretches."""
    path = []
    stretches = []
    distance_m = 0
    duration_s = 0
    meters_by_highway = Counter()
    for section in route_data["sections"]:
        section_points = flexpolyline.decode(section["polyline"])
        # Span offsets point into this section's polyline; shift them onto the joined path.
        points_before_section = len(path)
        for span in section.get("spans", []):
            highway = _main_highway(span)
            if highway:
                meters_by_highway[highway] += span["length"]
            stretches.append(
                RouteStretch(
                    start_point_index=points_before_section + span["offset"],
                    length_m=span["length"],
                    duration_s=span["duration"],
                )
            )
        path.extend(section_points)
        distance_m += section["summary"]["length"]
        duration_s += section["summary"]["duration"]

    sections = route_data["sections"]
    return TruckRoute(
        path=path,
        stretches=stretches,
        distance_m=distance_m,
        duration_s=duration_s,
        departure_time=datetime.fromisoformat(sections[0]["departure"]["time"]),
        arrival_time=datetime.fromisoformat(sections[-1]["arrival"]["time"]),
        highways=tuple(name for name, _ in meters_by_highway.most_common(HIGHWAY_NAME_COUNT)),
    )


def fetch_truck_routes(origin, destination, departure_time, load_weight_lb, via=None):
    """One HERE request: the main route plus any alternatives, fastest first.

    `via` is an optional (lat, lng) the route must pass through.
    """
    if departure_time.tzinfo is None:
        raise ValueError("departure_time must include a timezone.")
    params = {
        "transportMode": "truck",
        "origin": f"{origin.latitude},{origin.longitude}",
        "destination": f"{destination.latitude},{destination.longitude}",
        "departureTime": departure_time.isoformat(),
        "alternatives": ALTERNATIVE_ROUTE_COUNT,
        "return": "polyline,summary",
        # HERE merges spans unless a requested attribute changes along the road.
        # dynamicSpeedInfo splits them wherever the expected speed changes, which
        # is exactly where per-stretch drive times matter for checkpoint ETAs.
        # routeNumbers names the highway each span is on.
        "spans": "dynamicSpeedInfo,routeNumbers,length,duration",
        "vehicle[grossWeight]": gross_weight_kg(load_weight_lb),
    }
    if via is not None:
        # passThrough keeps the truck moving through the point instead of stopping there.
        params["via"] = f"{via[0]},{via[1]}!passThrough=true"
    data = _call_here(HERE_ROUTES_URL, params)
    routes = [_parse_route(route_data) for route_data in data.get("routes", [])]
    if not routes:
        raise NoRouteError("HERE found no truck route between these places.")
    return sorted(routes, key=lambda route: route.duration_s)


def _detour_point(origin, destination, offset_fraction):
    """A point beside the trip's midpoint, perpendicular to the straight line."""
    mid_lat = (origin.latitude + destination.latitude) / 2
    mid_lng = (origin.longitude + destination.longitude) / 2
    # Shrink longitude so the perpendicular is a true right angle on the ground.
    lng_scale = cos(radians(mid_lat))
    east = (destination.longitude - origin.longitude) * lng_scale
    north = destination.latitude - origin.latitude
    # Rotating (east, north) by 90 degrees gives (-north, east).
    return (
        mid_lat + east * offset_fraction,
        mid_lng - north * offset_fraction / lng_scale,
    )


def _road_cells(route):
    return {
        (round(lat, ROAD_GRID_DECIMALS), round(lng, ROAD_GRID_DECIMALS))
        for lat, lng in route.path
    }


def _mostly_same_road(route_a, route_b):
    cells_a, cells_b = _road_cells(route_a), _road_cells(route_b)
    shared = len(cells_a & cells_b)
    return shared / min(len(cells_a), len(cells_b)) >= SAME_ROAD_OVERLAP_RATIO


def fetch_route_options(origin, destination, departure_time, load_weight_lb):
    """Up to 3 distinct truck routes, fastest first.

    Uses HERE's alternatives first, then fills any gap with forced detours.
    Returns fewer than 3 when no reasonable distinct detour exists (e.g. a
    single highway along a coast), rather than inventing a pointless route.
    """
    routes = fetch_truck_routes(origin, destination, departure_time, load_weight_lb)
    fastest_duration_s = routes[0].duration_s

    for offset_fraction in DETOUR_OFFSET_FRACTIONS:
        if len(routes) >= TARGET_ROUTE_COUNT:
            break
        via = _detour_point(origin, destination, offset_fraction)
        try:
            detour = fetch_truck_routes(origin, destination, departure_time, load_weight_lb, via=via)[0]
        except RoutingError:
            # The point may be in water or have no truck-legal road nearby; try the next one.
            continue
        if detour.duration_s > fastest_duration_s * MAX_DETOUR_DURATION_RATIO:
            continue
        if any(_mostly_same_road(detour, existing) for existing in routes):
            continue
        routes.append(replace(detour, detour_via=via))

    return sorted(routes[:TARGET_ROUTE_COUNT], key=lambda route: route.duration_s)
