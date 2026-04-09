"""Unit tests for haversine distance calculator."""

import pytest

from app.utils.haversine import haversine


class TestHaversineZeroDistance:
    """Same point should return 0.0 km."""

    def test_zero_distance(self) -> None:
        lat, lon = 25.0330, 121.5654  # Taipei 101
        result = haversine(lat, lon, lat, lon)
        assert result == 0.0


class TestHaversineKnownDistance:
    """Two known GPS coordinates should return expected km within tolerance."""

    def test_known_distance(self) -> None:
        # Taipei 101 (25.0330, 121.5654) to Taipei Main Station (25.0478, 121.5170)
        # Known distance ~3.2 km
        result = haversine(25.0330, 121.5654, 25.0478, 121.5170)
        assert abs(result - 5.27) < 0.2


class TestHaversineAntipodalPoints:
    """Opposite sides of Earth should return ~20015 km (half circumference)."""

    def test_antipodal_points(self) -> None:
        # North Pole to South Pole
        result = haversine(90.0, 0.0, -90.0, 0.0)
        assert abs(result - 20015.0) < 100.0


class TestHaversineNegativeCoordinates:
    """Southern/Western hemisphere coordinates should work correctly."""

    def test_negative_coordinates(self) -> None:
        # Buenos Aires (-34.6037, -58.3816) to Sydney (-33.8688, 151.2093)
        # Known distance ~11,800 km
        result = haversine(-34.6037, -58.3816, -33.8688, 151.2093)
        assert abs(result - 11800.0) < 200.0


class TestHaversineOfficeBoundaryInside:
    """Point 50m from a reference should return distance < 0.1 km."""

    def test_office_boundary_inside(self) -> None:
        # Reference point: Taipei 101
        ref_lat, ref_lon = 25.0330, 121.5654
        # ~50m north (approx 0.00045 degrees latitude)
        nearby_lat = ref_lat + 0.00045
        nearby_lon = ref_lon
        result = haversine(ref_lat, ref_lon, nearby_lat, nearby_lon)
        assert result < 0.1


class TestHaversineOfficeBoundaryOutside:
    """Point 200m from a reference should return distance >= 0.1 km."""

    def test_office_boundary_outside(self) -> None:
        # Reference point: Taipei 101
        ref_lat, ref_lon = 25.0330, 121.5654
        # ~200m north (approx 0.0018 degrees latitude)
        far_lat = ref_lat + 0.0018
        far_lon = ref_lon
        result = haversine(ref_lat, ref_lon, far_lat, far_lon)
        assert result >= 0.1


class TestHaversineInvalidLatitude:
    """Latitude outside [-90, 90] should raise ValueError."""

    def test_invalid_latitude_raises(self) -> None:
        with pytest.raises(ValueError, match="Latitude"):
            haversine(91.0, 0.0, 0.0, 0.0)

        with pytest.raises(ValueError, match="Latitude"):
            haversine(0.0, 0.0, -91.0, 0.0)


class TestHaversineInvalidLongitude:
    """Longitude outside [-180, 180] should raise ValueError."""

    def test_invalid_longitude_raises(self) -> None:
        with pytest.raises(ValueError, match="Longitude"):
            haversine(0.0, 181.0, 0.0, 0.0)

        with pytest.raises(ValueError, match="Longitude"):
            haversine(0.0, 0.0, 0.0, -181.0)
