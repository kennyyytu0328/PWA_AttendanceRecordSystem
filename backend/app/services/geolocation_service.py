"""Geolocation service — determines work mode based on GPS coordinates."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import WorkMode
from app.repositories.system_config_repository import get_office_location
from app.utils.haversine import haversine

__all__ = ["WorkModeResult", "determine_work_mode"]

_OFFICE_RADIUS_KM: float = 2.0  # 2 km (campus)
_ACCURACY_THRESHOLD_M: float = 500.0


@dataclass(frozen=True)
class WorkModeResult:
    """Immutable result of a geolocation-based work-mode determination."""

    work_mode: WorkMode
    distance_km: float
    accuracy: float
    is_low_accuracy: bool


async def determine_work_mode(
    session: AsyncSession,
    latitude: float,
    longitude: float,
    accuracy: float,
) -> WorkModeResult:
    """Determine whether the employee is working from office or remotely.

    Args:
        session: Active async database session.
        latitude: Employee GPS latitude in decimal degrees.
        longitude: Employee GPS longitude in decimal degrees.
        accuracy: GPS accuracy in metres reported by the device.

    Returns:
        A frozen WorkModeResult with work_mode, distance_km, accuracy,
        and is_low_accuracy fields.

    Raises:
        ValueError: If the office location has not been configured in
            the system_config table.
    """
    office = await get_office_location(session)
    if office is None:
        raise ValueError("Office location not configured")

    office_lat: float = office["latitude"]
    office_lon: float = office["longitude"]

    distance_km: float = haversine(latitude, longitude, office_lat, office_lon)
    work_mode: WorkMode = (
        WorkMode.OFFICE if distance_km < _OFFICE_RADIUS_KM else WorkMode.WFH
    )
    is_low_accuracy: bool = accuracy > _ACCURACY_THRESHOLD_M

    return WorkModeResult(
        work_mode=work_mode,
        distance_km=distance_km,
        accuracy=accuracy,
        is_low_accuracy=is_low_accuracy,
    )
