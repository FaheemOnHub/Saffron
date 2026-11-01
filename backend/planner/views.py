from datetime import datetime, timedelta, timezone

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from planner.checkpoints import CHECKPOINT_INTERVAL_OPTIONS_MILES
from planner.routing import NoRouteError, PlaceNotFoundError, RoutingError
from planner.serializers import serialize_trip_plan
from planner.trip_planner import plan_trip
from planner.weather import WeatherError

MAX_PLACE_LENGTH = 200
# Loads above this are beyond any normal permit; likely a typo (e.g. kg vs lb).
MAX_LOAD_WEIGHT_LB = 80_000
DEFAULT_CHECKPOINT_INTERVAL_MILES = 25
# A little slack so "leave now" still passes after the form sits open a while.
DEPARTURE_PAST_GRACE = timedelta(hours=1)
# Forecasts lose skill quickly past a week, and a multi-day trip still has to
# fit inside Open-Meteo's ~16-day window.
DEPARTURE_MAX_AHEAD = timedelta(days=7)


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
        errors["departure_time"] = "Use an ISO 8601 date-time with a timezone, e.g. 2026-11-02T08:00:00-06:00."
    else:
        if departure.tzinfo is None:
            errors["departure_time"] = "Include a timezone offset, e.g. -06:00 or Z."
        elif departure < now - DEPARTURE_PAST_GRACE:
            errors["departure_time"] = "Departure can't be in the past."
        elif departure > now + DEPARTURE_MAX_AHEAD:
            errors["departure_time"] = "Departure must be within the next 7 days so forecasts are reliable."
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
    except PlaceNotFoundError as error:
        return JsonResponse({"detail": str(error)}, status=400)
    except NoRouteError as error:
        return JsonResponse({"detail": str(error)}, status=422)
    except (RoutingError, WeatherError) as error:
        # Upstream API trouble, not the driver's fault.
        return JsonResponse({"detail": str(error)}, status=502)

    return JsonResponse(serialize_trip_plan(plan))
