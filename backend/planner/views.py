from datetime import datetime, timezone

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from planner.checkpoints import CHECKPOINT_INTERVAL_OPTIONS_MILES
from planner.routing import NoRouteError, PlaceNotFoundError, RoutingError, suggest_places
from planner.serializers import serialize_trip_plan
from planner.trip_planner import DepartureError, check_departure_window, plan_trip
from planner.weather import WeatherError

MAX_PLACE_LENGTH = 200
# Below this, autocomplete matches are too broad to be useful.
MIN_SUGGEST_QUERY_LENGTH = 2
# Loads above this are beyond any normal permit; likely a typo (e.g. kg vs lb).
MAX_LOAD_WEIGHT_LB = 80_000
DEFAULT_CHECKPOINT_INTERVAL_MILES = 25


def _parse_trip_request(query, now):
    """Return (cleaned values, field errors)."""
    errors = {}
    cleaned = {}

    for field in ("origin", "destination"):
        value = query.get(field, "").strip()
        if not value:
            errors[field] = "Required."
        elif len(value) > MAX_PLACE_LENGTH:
            errors[field] = f"Must be {MAX_PLACE_LENGTH} characters or fewer."
        cleaned[field] = value
    if not errors and cleaned["origin"].lower() == cleaned["destination"].lower():
        errors["destination"] = "Must be different from the origin."

    raw_departure = query.get("departure_time", "").strip()
    try:
        departure = datetime.fromisoformat(raw_departure)
    except ValueError:
        errors["departure_time"] = "Use an ISO 8601 date-time, e.g. 2026-11-02T08:00."
    else:
        # Without an offset it's local time at the origin; plan_trip checks it
        # once the origin's zone is known. With an offset we can check now.
        if departure.tzinfo is not None:
            try:
                check_departure_window(departure, now)
            except DepartureError as error:
                errors["departure_time"] = str(error)
        cleaned["departure_time"] = departure

    raw_load = query.get("load_weight_lb", "").strip()
    try:
        load = float(raw_load)
    except ValueError:
        errors["load_weight_lb"] = "Enter the load weight in pounds."
    else:
        # Written as "not in range" so NaN (which fails every comparison) is rejected too.
        if not 0 <= load <= MAX_LOAD_WEIGHT_LB:
            errors["load_weight_lb"] = f"Must be between 0 and {MAX_LOAD_WEIGHT_LB:,} lb."
        else:
            cleaned["load_weight_lb"] = round(load)

    raw_interval = query.get("checkpoint_interval_miles", str(DEFAULT_CHECKPOINT_INTERVAL_MILES))
    try:
        interval = int(raw_interval)
    except ValueError:
        interval = None
    if interval not in CHECKPOINT_INTERVAL_OPTIONS_MILES:
        allowed = ", ".join(str(option) for option in CHECKPOINT_INTERVAL_OPTIONS_MILES)
        errors["checkpoint_interval_miles"] = f"Must be one of {allowed}."
    cleaned["checkpoint_interval_miles"] = interval

    return cleaned, errors


@require_GET
def health(request):
    """Liveness check for the host; doesn't call any third-party API."""
    return JsonResponse({"status": "ok"})


@require_GET
def places(request):
    """Autocomplete suggestions for the From/To fields."""
    query = request.GET.get("q", "").strip()[:MAX_PLACE_LENGTH]
    if len(query) < MIN_SUGGEST_QUERY_LENGTH:
        return JsonResponse({"suggestions": []})
    try:
        suggestions = suggest_places(query)
    except RoutingError as error:
        return JsonResponse({"detail": str(error)}, status=502)
    return JsonResponse({"suggestions": suggestions})


@require_GET
def trip_plan(request):
    cleaned, errors = _parse_trip_request(request.GET, now=datetime.now(timezone.utc))
    if errors:
        return JsonResponse({"errors": errors}, status=400)

    try:
        plan = plan_trip(
            origin_query=cleaned["origin"],
            destination_query=cleaned["destination"],
            departure_time=cleaned["departure_time"],
            load_weight_lb=cleaned["load_weight_lb"],
            checkpoint_interval_miles=cleaned["checkpoint_interval_miles"],
        )
    except DepartureError as error:
        return JsonResponse({"errors": {"departure_time": f"{error} (read as local time at the origin)"}}, status=400)
    except PlaceNotFoundError as error:
        return JsonResponse({"detail": str(error)}, status=400)
    except NoRouteError as error:
        return JsonResponse({"detail": str(error)}, status=422)
    except (RoutingError, WeatherError) as error:
        # Upstream API trouble, not the driver's fault.
        return JsonResponse({"detail": str(error)}, status=502)

    return JsonResponse(serialize_trip_plan(plan))
