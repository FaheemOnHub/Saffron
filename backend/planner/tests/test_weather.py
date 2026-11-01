from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from planner.weather import (
    POINTS_PER_REQUEST,
    ForecastRequest,
    WeatherError,
    forecast_for,
)

NOW = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
CENTRAL = timezone(timedelta(hours=-6))


def hourly_location(start, hours, wind=None, gust=None, rain=None, showers=None, snow=None):
    """Open-Meteo-shaped forecast for one point; each field is a list or a constant."""
    def series(value, default):
        if isinstance(value, list):
            return value
        return [default if value is None else value] * hours

    return {
        "hourly": {
            "time": [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)],
            "wind_speed_10m": series(wind, 5.0),
            "wind_gusts_10m": series(gust, 8.0),
            "rain": series(rain, 0.0),
            "showers": series(showers, 0.0),
            "snowfall": series(snow, 0.0),
        }
    }


def fake_response(body, status_code=200):
    response = Mock()
    response.ok = status_code < 400
    response.status_code = status_code
    response.json.return_value = body
    response.text = str(body)
    return response


class ForecastHourTests(SimpleTestCase):
    @patch("planner.weather.requests.get")
    def test_precipitation_uses_hour_ending_after_eta_and_wind_uses_nearest(self, mock_get):
        start = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
        # Hours 07:00 08:00 09:00 10:00
        mock_get.return_value = fake_response(hourly_location(
            start, 4, wind=[10.0, 20.0, 30.0, 40.0], rain=[0.01, 0.02, 0.03, 0.04],
        ))
        # 08:40 -> rain from the 09:00 slot (08:00-09:00 total), wind nearest is 09:00.
        reading = forecast_for([ForecastRequest(32.0, -96.0, start + timedelta(hours=1, minutes=40))], now=NOW)[0]
        self.assertEqual(reading.rain_in_per_hr, 0.03)
        self.assertEqual(reading.wind_mph, 30.0)
        self.assertEqual(reading.forecast_hour, start + timedelta(hours=2))

    @patch("planner.weather.requests.get")
    def test_wind_rounds_down_before_half_past(self, mock_get):
        start = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
        mock_get.return_value = fake_response(hourly_location(start, 4, wind=[10.0, 20.0, 30.0, 40.0]))
        reading = forecast_for([ForecastRequest(32.0, -96.0, start + timedelta(hours=1, minutes=10))], now=NOW)[0]
        self.assertEqual(reading.wind_mph, 20.0)

    @patch("planner.weather.requests.get")
    def test_on_the_hour_uses_that_hour(self, mock_get):
        start = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
        mock_get.return_value = fake_response(hourly_location(start, 4, rain=[0.01, 0.02, 0.03, 0.04]))
        reading = forecast_for([ForecastRequest(32.0, -96.0, start + timedelta(hours=1))], now=NOW)[0]
        self.assertEqual(reading.rain_in_per_hr, 0.02)

    @patch("planner.weather.requests.get")
    def test_local_time_is_converted_to_utc(self, mock_get):
        start = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)
        mock_get.return_value = fake_response(hourly_location(start, 3, wind=[1.0, 2.0, 3.0]))
        # 09:00 Central = 15:00 UTC
        when = datetime(2026, 11, 2, 9, 0, tzinfo=CENTRAL)
        reading = forecast_for([ForecastRequest(32.0, -96.0, when)], now=NOW)[0]
        self.assertEqual(reading.wind_mph, 2.0)
        self.assertEqual(mock_get.call_args.kwargs["params"]["start_hour"], "2026-11-02T14:00")


class ReadingValuesTests(SimpleTestCase):
    @patch("planner.weather.requests.get")
    def test_rain_includes_showers_and_snow_is_inches(self, mock_get):
        start = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
        mock_get.return_value = fake_response(hourly_location(start, 3, rain=0.1, showers=0.05, snow=0.7, gust=31.0))
        reading = forecast_for([ForecastRequest(32.0, -96.0, start + timedelta(hours=1))], now=NOW)[0]
        self.assertAlmostEqual(reading.rain_in_per_hr, 0.15)
        self.assertEqual(reading.snow_in_per_hr, 0.7)
        self.assertEqual(reading.wind_gust_mph, 31.0)

    @patch("planner.weather.requests.get")
    def test_null_values_mean_no_forecast(self, mock_get):
        start = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
        mock_get.return_value = fake_response(hourly_location(start, 3, wind=[5.0, None, None]))
        reading = forecast_for([ForecastRequest(32.0, -96.0, start + timedelta(hours=1))], now=NOW)[0]
        self.assertIsNone(reading)

    @patch("planner.weather.requests.get")
    def test_missing_optional_showers_and_gusts_count_as_zero(self, mock_get):
        start = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
        location = hourly_location(start, 3, rain=0.2)
        location["hourly"]["showers"] = [None] * 3
        location["hourly"]["wind_gusts_10m"] = [None] * 3
        mock_get.return_value = fake_response(location)
        reading = forecast_for([ForecastRequest(32.0, -96.0, start + timedelta(hours=1))], now=NOW)[0]
        self.assertEqual(reading.rain_in_per_hr, 0.2)
        self.assertEqual(reading.wind_gust_mph, 0.0)


class BatchingTests(SimpleTestCase):
    @patch("planner.weather.requests.get")
    def test_points_are_sent_together_and_answers_keep_order(self, mock_get):
        start = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
        mock_get.return_value = fake_response([
            hourly_location(start, 3, wind=11.0), hourly_location(start, 3, wind=22.0),
        ])
        readings = forecast_for([
            ForecastRequest(32.0, -96.0, start + timedelta(hours=1)),
            ForecastRequest(31.0, -95.5, start + timedelta(hours=1)),
        ], now=NOW)
        self.assertEqual([r.wind_mph for r in readings], [11.0, 22.0])
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["latitude"], "32.0000,31.0000")
        self.assertEqual(params["wind_speed_unit"], "mph")
        self.assertEqual(params["precipitation_unit"], "inch")

    @patch("planner.weather.requests.get")
    def test_large_requests_are_split(self, mock_get):
        start = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
        mock_get.side_effect = lambda url, params, timeout: fake_response(
            [hourly_location(start, 3)] * len(params["latitude"].split(","))
        )
        points = [ForecastRequest(32.0, -96.0, start + timedelta(hours=1))] * (POINTS_PER_REQUEST + 5)
        readings = forecast_for(points, now=NOW)
        self.assertEqual(len(readings), POINTS_PER_REQUEST + 5)
        self.assertEqual(mock_get.call_count, 2)

    @patch("planner.weather.requests.get")
    def test_empty_input_makes_no_request(self, mock_get):
        self.assertEqual(forecast_for([], now=NOW), [])
        mock_get.assert_not_called()


class ForecastHorizonTests(SimpleTestCase):
    @patch("planner.weather.requests.get")
    def test_window_end_is_capped_at_horizon(self, mock_get):
        start = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
        mock_get.return_value = fake_response([hourly_location(start, 3), hourly_location(start, 3)])
        readings = forecast_for([
            ForecastRequest(32.0, -96.0, start + timedelta(hours=1)),
            ForecastRequest(32.0, -96.0, NOW + timedelta(days=30)),
        ], now=NOW)
        self.assertEqual(mock_get.call_args.kwargs["params"]["end_hour"], "2026-11-17T06:00")
        self.assertIsNotNone(readings[0])
        self.assertIsNone(readings[1])

    @patch("planner.weather.requests.get")
    def test_all_points_past_horizon_skip_the_request(self, mock_get):
        readings = forecast_for([ForecastRequest(32.0, -96.0, NOW + timedelta(days=20))], now=NOW)
        self.assertEqual(readings, [None])
        mock_get.assert_not_called()


class FailureTests(SimpleTestCase):
    def test_naive_time_is_rejected(self):
        with self.assertRaises(ValueError):
            forecast_for([ForecastRequest(32.0, -96.0, datetime(2026, 11, 2, 8, 0))], now=NOW)

    @patch("planner.weather.requests.get")
    def test_http_error_uses_open_meteo_reason(self, mock_get):
        mock_get.return_value = fake_response({"error": True, "reason": "Latitude must be in range"}, 400)
        with self.assertRaisesMessage(WeatherError, "Latitude must be in range"):
            forecast_for([ForecastRequest(32.0, -96.0, NOW + timedelta(hours=1))], now=NOW)

    @patch("planner.weather.requests.get", side_effect=requests.Timeout("slow"))
    def test_network_error_raises_weather_error(self, _mock_get):
        with self.assertRaisesMessage(WeatherError, "Could not reach Open-Meteo"):
            forecast_for([ForecastRequest(32.0, -96.0, NOW + timedelta(hours=1))], now=NOW)

    @patch("planner.weather.requests.get")
    def test_wrong_number_of_forecasts_raises(self, mock_get):
        start = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
        mock_get.return_value = fake_response([hourly_location(start, 3)])
        with self.assertRaisesMessage(WeatherError, "1 forecasts for 2 points"):
            forecast_for([ForecastRequest(32.0, -96.0, start)] * 2, now=NOW)
