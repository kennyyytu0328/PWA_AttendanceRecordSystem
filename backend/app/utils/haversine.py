"""Haversine distance calculator for GPS coordinates."""

import math
from typing import Final

__all__ = ["haversine", "EARTH_RADIUS_KM"]

EARTH_RADIUS_KM: Final[float] = 6371.0

_LAT_MIN: Final[float] = -90.0
_LAT_MAX: Final[float] = 90.0
_LON_MIN: Final[float] = -180.0
_LON_MAX: Final[float] = 180.0


def _validate_range(value: float, min_val: float, max_val: float, name: str) -> None:
    """Validate that a single coordinate value is within bounds.

    Args:
        value: The coordinate value to check.
        min_val: Minimum allowed value (inclusive).
        max_val: Maximum allowed value (inclusive).
        name: Human-readable name for error messages (e.g. "Latitude").

    Raises:
        ValueError: If value is outside [min_val, max_val].
    """
    if not (min_val <= value <= max_val):
        raise ValueError(
            f"{name} must be between {min_val} and {max_val} degrees, got {value}"
        )


def _validate_coordinates(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> None:
    """Validate that all four coordinates are within valid ranges.

    Raises:
        ValueError: If any coordinate is out of range.
    """
    _validate_range(lat1, _LAT_MIN, _LAT_MAX, "Latitude")
    _validate_range(lat2, _LAT_MIN, _LAT_MAX, "Latitude")
    _validate_range(lon1, _LON_MIN, _LON_MAX, "Longitude")
    _validate_range(lon2, _LON_MIN, _LON_MAX, "Longitude")


def haversine(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculate the great-circle distance between two points on Earth.

    Uses the Haversine formula to compute the shortest distance over
    the Earth's surface between two GPS coordinates.

    Args:
        lat1: Latitude of point 1 in decimal degrees [-90, 90].
        lon1: Longitude of point 1 in decimal degrees [-180, 180].
        lat2: Latitude of point 2 in decimal degrees [-90, 90].
        lon2: Longitude of point 2 in decimal degrees [-180, 180].

    Returns:
        Distance in kilometers.

    Raises:
        ValueError: If any coordinate is outside its valid range.
    """
    _validate_coordinates(lat1, lon1, lat2, lon2)

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return EARTH_RADIUS_KM * c
