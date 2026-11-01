"""
Time zone of a point on the map, looked up offline.

tzfpy bundles the world's time zone boundaries, so this needs no API call and
is fast enough to run for every checkpoint. Times are shown in the local zone
of the place they describe: departure at the origin, arrival at the
destination, each checkpoint where it is.
"""

from zoneinfo import ZoneInfo

from tzfpy import get_tz

FALLBACK_TIMEZONE = "UTC"


def timezone_name_at(latitude, longitude):
    # tzfpy takes longitude first.
    return get_tz(longitude, latitude) or FALLBACK_TIMEZONE


def localize(naive_moment, timezone_name):
    """Attach a zone to a wall-clock time typed by the driver.

    On the night clocks fall back, an hour like 1:30 AM happens twice; Python's
    default (fold=0) takes the first one, which is the earlier, safer reading.
    """
    return naive_moment.replace(tzinfo=ZoneInfo(timezone_name))
