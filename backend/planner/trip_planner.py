"""
Runs the whole pipeline for one trip request:
geocode -> truck routes -> checkpoints -> weather -> risk -> ranking.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from planner.assessment import assess_route, rank_routes, rate_checkpoints
from planner.checkpoints import place_checkpoints
from planner.corridor import corridor_forecast
from planner.routing import fetch_route_options, geocode_place
from planner.weather import ForecastRequest, forecast_for


@dataclass(frozen=True)
class TripPlan:
    origin: object  # routing.Place
    destination: object  # routing.Place
    load_weight_lb: int
    checkpoint_interval_miles: int
    routes: list  # assessment.RouteAssessment, best first
    corridor: object  # corridor.CorridorForecast for the heatmap


def plan_trip(origin_query, destination_query, departure_time, load_weight_lb, checkpoint_interval_miles):
    origin = geocode_place(origin_query)
    destination = geocode_place(destination_query)
    routes = fetch_route_options(origin, destination, departure_time, load_weight_lb)
    checkpoints_per_route = [place_checkpoints(route, checkpoint_interval_miles) for route in routes]

    # One batched weather lookup for every checkpoint on every route, run
    # alongside the corridor heatmap lookup since neither depends on the other.
    all_checkpoints = [checkpoint for checkpoints in checkpoints_per_route for checkpoint in checkpoints]
    with ThreadPoolExecutor(max_workers=2) as pool:
        checkpoint_weather_job = pool.submit(forecast_for, [
            ForecastRequest(checkpoint.latitude, checkpoint.longitude, checkpoint.eta)
            for checkpoint in all_checkpoints
        ])
        corridor_job = pool.submit(corridor_forecast, routes, departure_time, load_weight_lb)
        readings = checkpoint_weather_job.result()
        corridor = corridor_job.result()

    assessments = []
    reading_position = 0
    for route, checkpoints in zip(routes, checkpoints_per_route):
        route_readings = readings[reading_position:reading_position + len(checkpoints)]
        reading_position += len(checkpoints)
        rated = rate_checkpoints(checkpoints, route_readings, load_weight_lb)
        assessments.append(assess_route(route, rated))

    return TripPlan(
        origin=origin,
        destination=destination,
        load_weight_lb=load_weight_lb,
        checkpoint_interval_miles=checkpoint_interval_miles,
        routes=rank_routes(assessments),
        corridor=corridor,
    )
