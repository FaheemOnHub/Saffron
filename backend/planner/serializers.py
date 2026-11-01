"""Turn planner results into the JSON shape the React app reads."""

from planner.risk import RiskLevel

# Plenty for a map line: 5 decimals of lat/lng is about 1 m.
COORDINATE_DECIMALS = 5


def level_key(level):
    return None if level is None else level.name.lower()


def _place(place):
    return {"label": place.label, "lat": place.latitude, "lng": place.longitude}


def _checkpoint(rated):
    checkpoint, weather, risk = rated.checkpoint, rated.weather, rated.risk
    return {
        "sequence": checkpoint.sequence,
        "distance_miles": round(checkpoint.distance_miles, 1),
        "lat": round(checkpoint.latitude, COORDINATE_DECIMALS),
        "lng": round(checkpoint.longitude, COORDINATE_DECIMALS),
        "eta": checkpoint.eta.isoformat(),
        "coverage_miles": round(checkpoint.coverage_miles, 2),
        "forecast_available": weather is not None,
        "weather": None if weather is None else {
            "wind_mph": weather.wind_mph,
            "wind_gust_mph": weather.wind_gust_mph,
            "rain_in_per_hr": round(weather.rain_in_per_hr, 3),
            "snow_in_per_hr": round(weather.snow_in_per_hr, 3),
            "forecast_hour": weather.forecast_hour.isoformat(),
        },
        "risk": None if risk is None else {
            "level": level_key(risk.level),
            "wind_level": level_key(risk.wind_level),
            "rain_level": level_key(risk.rain_level),
            "snow_level": level_key(risk.snow_level),
            "raised_by_load": risk.raised_by_load,
        },
        "gust_warning": rated.gust_warning,
    }


def _route(assessment):
    route = assessment.route
    return {
        "id": f"route-{assessment.rank}",
        "rank": assessment.rank,
        "is_recommended": assessment.is_recommended,
        "recommendation_reason": assessment.recommendation_reason,
        "is_detour": route.detour_via is not None,
        "distance_miles": round(route.distance_m / 1609.344, 1),
        "duration_s": route.duration_s,
        "departure_time": route.departure_time.isoformat(),
        "arrival_time": route.arrival_time.isoformat(),
        "risk_summary": {
            "worst_level": level_key(assessment.worst_level),
            "average_risk": round(assessment.average_risk, 2),
            "miles_by_level": {
                level_key(level): round(assessment.miles_by_level[level], 1) for level in RiskLevel
            },
            "unknown_miles": round(assessment.unknown_miles, 1),
            "gust_warning_count": assessment.gust_warning_count,
        },
        "path": [
            [round(lat, COORDINATE_DECIMALS), round(lng, COORDINATE_DECIMALS)] for lat, lng in route.path
        ],
        "checkpoints": [_checkpoint(rated) for rated in assessment.checkpoints],
    }


def serialize_trip_plan(plan):
    return {
        "origin": _place(plan.origin),
        "destination": _place(plan.destination),
        "load_weight_lb": plan.load_weight_lb,
        "checkpoint_interval_miles": plan.checkpoint_interval_miles,
        "risk_levels": [{"key": level_key(level), "label": level.label, "value": int(level)} for level in RiskLevel],
        "routes": [_route(assessment) for assessment in plan.routes],
    }
