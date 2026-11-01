"""
Hourly forecasts from Open-Meteo for points the truck will pass at known times.

Units are requested directly in mph and inches, matching the risk table, so
no conversion happens here.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 20
# Open-Meteo takes many coordinates per request; batching keeps URLs a sane length.
POINTS_PER_REQUEST = 100
# Batches are independent, so they're sent in parallel to cut waiting time.
PARALLEL_REQUESTS = 4
HOURLY_FIELDS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"
ONE_HOUR = timedelta(hours=1)
# Open-Meteo rejects the whole request if the window ends past its ~16-day
# forecast, so we stop the window at 15 days and treat later points as unknown.
FORECAST_HORIZON = timedelta(days=15)


class WeatherError(Exception):
    """Open-Meteo couldn't be reached or returned an error."""


@dataclass(frozen=True)
class WeatherReading:
    wind_mph: float
    wind_gust_mph: float
    rain_in_per_hr: float
    snow_in_per_hr: float
    forecast_hour: datetime  # the UTC hour the precipitation totals cover up to


@dataclass(frozen=True)
class ForecastRequest:
    latitude: float
    longitude: float
    when: datetime  # timezone-aware time the truck is at this point


def _floor_hour(moment):
    return moment.replace(minute=0, second=0, microsecond=0)


def _ceil_hour(moment):
    floored = _floor_hour(moment)
    return floored if floored == moment else floored + ONE_HOUR


def _reading_at(hourly, hour_index, when):
    """Pick the forecast hour for a moment in time.

    Open-Meteo's rain/snow at hour H is the total for the hour *ending* at H,
    so the hour the truck is in is the slot at or after `when`. Wind is a
    snapshot at H, so we take the nearest hour instead.
    """
    precipitation_hour = _ceil_hour(when)
    wind_hour = _floor_hour(when + timedelta(minutes=30))
    precipitation_slot = hour_index.get(precipitation_hour)
    wind_slot = hour_index.get(wind_hour)
    if precipitation_slot is None or wind_slot is None:
        return None

    values = {
        "wind": hourly["wind_speed_10m"][wind_slot],
        "gust": hourly["wind_gusts_10m"][wind_slot],
        "rain": hourly["rain"][precipitation_slot],
        "showers": hourly["showers"][precipitation_slot],
        "snow": hourly["snowfall"][precipitation_slot],
    }
    # Open-Meteo returns null past the end of its forecast models.
    if any(values[name] is None for name in ("wind", "rain", "snow")):
        return None
    return WeatherReading(
        wind_mph=values["wind"],
        wind_gust_mph=values["gust"] or 0.0,
        # Open-Meteo splits convective showers from steady rain; both are rain on the road.
        rain_in_per_hr=values["rain"] + (values["showers"] or 0.0),
        snow_in_per_hr=values["snow"],
        forecast_hour=precipitation_hour,
    )


def _fetch_hourly(coordinates, window_start, window_end):
    """Hourly series for each (lat, lng) between two UTC hours, inclusive.

    Returns one (hourly data, {utc hour: slot}) pair per coordinate, in order.
    """
    params = {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in coordinates),
        "longitude": ",".join(f"{lng:.4f}" for _, lng in coordinates),
        "hourly": HOURLY_FIELDS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        # Only fetch the hours we need instead of the full 16-day forecast.
        "start_hour": window_start.strftime("%Y-%m-%dT%H:%M"),
        "end_hour": window_end.strftime("%Y-%m-%dT%H:%M"),
    }
    try:
        response = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as error:
        raise WeatherError(f"Could not reach Open-Meteo: {error}") from error
    if not response.ok:
        try:
            detail = response.json().get("reason", response.text)
        except ValueError:
            detail = response.text
        raise WeatherError(f"Open-Meteo request failed ({response.status_code}): {detail}")

    data = response.json()
    # A single location comes back as an object, several as a list.
    locations = data if isinstance(data, list) else [data]
    if len(locations) != len(coordinates):
        raise WeatherError(f"Open-Meteo returned {len(locations)} forecasts for {len(coordinates)} points.")

    series = []
    for location in locations:
        hourly = location["hourly"]
        hour_index = {
            datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc): slot
            for slot, stamp in enumerate(hourly["time"])
        }
        series.append((hourly, hour_index))
    return series


def _in_batches(items, fetch_batch):
    """Run fetch_batch over POINTS_PER_REQUEST-sized slices in parallel, keeping order."""
    batches = [items[start:start + POINTS_PER_REQUEST] for start in range(0, len(items), POINTS_PER_REQUEST)]
    if len(batches) <= 1:
        return [result for batch in batches for result in fetch_batch(batch)]
    with ThreadPoolExecutor(max_workers=PARALLEL_REQUESTS) as pool:
        return [result for batch_results in pool.map(fetch_batch, batches) for result in batch_results]


def _horizon_end(now):
    return _floor_hour(now) + FORECAST_HORIZON


def forecast_for(requests_list, now=None):
    """Forecast at each point for the time the truck is there.

    Returns readings in the same order as the input. A reading is None when the
    time falls outside the available forecast (Open-Meteo covers ~16 days).
    `now` is only passed in tests, to pin the forecast horizon.
    """
    now = now or datetime.now(timezone.utc)
    for request in requests_list:
        if request.when.tzinfo is None:
            raise ValueError("Forecast times must include a timezone.")

    def fetch_batch(batch):
        times_utc = [request.when.astimezone(timezone.utc) for request in batch]
        window_start = _floor_hour(min(times_utc)) - ONE_HOUR
        window_end = min(_ceil_hour(max(times_utc)) + ONE_HOUR, _horizon_end(now))
        if window_start > window_end:
            return [None] * len(batch)
        series = _fetch_hourly([(r.latitude, r.longitude) for r in batch], window_start, window_end)
        return [_reading_at(hourly, hour_index, when) for (hourly, hour_index), when in zip(series, times_utc)]

    return _in_batches(requests_list, fetch_batch)


def hourly_forecasts(coordinates, first_hour, hour_count, now=None):
    """Weather at each (lat, lng) for `hour_count` consecutive hours from `first_hour`.

    Returns one list per coordinate, each with `hour_count` readings (None
    where the hour is past the forecast horizon). Used for the corridor heatmap.
    """
    if first_hour.tzinfo is None:
        raise ValueError("first_hour must include a timezone.")
    now = now or datetime.now(timezone.utc)
    first_hour = _floor_hour(first_hour.astimezone(timezone.utc))
    hours = [first_hour + ONE_HOUR * offset for offset in range(hour_count)]
    window_end = min(hours[-1] + ONE_HOUR, _horizon_end(now))

    def fetch_batch(batch):
        if first_hour > window_end:
            return [[None] * hour_count for _ in batch]
        series = _fetch_hourly(batch, first_hour - ONE_HOUR, window_end)
        return [[_reading_at(hourly, hour_index, hour) for hour in hours] for hourly, hour_index in series]

    return _in_batches(list(coordinates), fetch_batch)
