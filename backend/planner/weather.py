"""
Hourly forecasts from Open-Meteo for points the truck will pass at known times.

Units are requested directly in mph and inches, matching the risk table, so
no conversion happens here.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 20
# Open-Meteo takes many coordinates per request; batching keeps URLs a sane length.
POINTS_PER_REQUEST = 100
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


def _fetch_batch(batch, now):
    times_utc = [request.when.astimezone(timezone.utc) for request in batch]
    window_start = _floor_hour(min(times_utc)) - ONE_HOUR
    window_end = min(_ceil_hour(max(times_utc)) + ONE_HOUR, _floor_hour(now) + FORECAST_HORIZON)
    if window_start > window_end:
        return [None] * len(batch)
    params = {
        "latitude": ",".join(f"{request.latitude:.4f}" for request in batch),
        "longitude": ",".join(f"{request.longitude:.4f}" for request in batch),
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
    if len(locations) != len(batch):
        raise WeatherError(f"Open-Meteo returned {len(locations)} forecasts for {len(batch)} points.")

    readings = []
    for location, when in zip(locations, times_utc):
        hourly = location["hourly"]
        hour_index = {
            datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc): slot
            for slot, stamp in enumerate(hourly["time"])
        }
        readings.append(_reading_at(hourly, hour_index, when))
    return readings


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
    readings = []
    for start in range(0, len(requests_list), POINTS_PER_REQUEST):
        readings.extend(_fetch_batch(requests_list[start:start + POINTS_PER_REQUEST], now))
    return readings
