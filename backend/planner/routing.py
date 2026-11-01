"""
Geocoding and truck routing through the HERE APIs.

Everything HERE-specific (URLs, parameter names, response shape, the
flexible polyline format) stays in this module, so the rest of the planner
works with plain Place / TruckRoute objects.
"""

from dataclasses import dataclass
from datetime import datetime

import flexpolyline
import requests
from django.conf import settings

HERE_GEOCODE_URL = "https://geocode.search.hereapi.com/v1/geocode"
HERE_ROUTES_URL = "https://router.hereapi.com/v8/routes"
REQUEST_TIMEOUT_SECONDS = 20

# HERE can return up to 6 alternatives; 2 alternatives + the main route = 3 options.
ALTERNATIVE_ROUTE_COUNT = 2

KG_PER_LB = 0.45359237
# The driver enters cargo weight, but truck routing needs gross weight.
# A typical empty tractor + 53 ft trailer weighs about 35,000 lb.
EMPTY_TRUCK_WEIGHT_LB = 35_000


class RoutingError(Exception):
    """A place can't be found, no route exists, or the HERE API failed."""


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
        raise RoutingError("Place name is empty.")
    data = _call_here(HERE_GEOCODE_URL, {"q": query, "limit": 1})
    items = data.get("items") or []
    if not items:
        raise RoutingError(f"Could not find a location for '{query}'.")
    best_match = items[0]
    return Place(
        label=best_match.get("title", query),
        latitude=best_match["position"]["lat"],
        longitude=best_match["position"]["lng"],
    )


def gross_weight_kg(load_weight_lb):
    return round((EMPTY_TRUCK_WEIGHT_LB + load_weight_lb) * KG_PER_LB)


def _parse_route(route_data):
    """Join a HERE route's sections into one continuous path with stretches."""
    path = []
    stretches = []
    distance_m = 0
    duration_s = 0
    for section in route_data["sections"]:
        section_points = flexpolyline.decode(section["polyline"])
        # Span offsets point into this section's polyline; shift them onto the joined path.
        points_before_section = len(path)
        for span in section.get("spans", []):
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
    )


def fetch_truck_routes(origin, destination, departure_time, load_weight_lb):
    """Return up to 3 truck routes from HERE, fastest first."""
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
        "spans": "dynamicSpeedInfo,length,duration",
        "vehicle[grossWeight]": gross_weight_kg(load_weight_lb),
    }
    data = _call_here(HERE_ROUTES_URL, params)
    routes = [_parse_route(route_data) for route_data in data.get("routes", [])]
    if not routes:
        raise RoutingError("HERE found no truck route between these places.")
    return sorted(routes, key=lambda route: route.duration_s)
