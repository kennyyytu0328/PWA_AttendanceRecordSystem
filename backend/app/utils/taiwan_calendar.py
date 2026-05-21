"""Taiwan workday calendar utility.

Parses calendar JSON from ruyut/TaiwanCalendar (sourced from 行政院人事行政總處).
Data URL: https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json
"""

from __future__ import annotations

import calendar
import datetime
import enum
from dataclasses import dataclass
from typing import Any

import httpx

_MAKEUP_KEYWORDS = ("補行上班", "補班")
_WEEKDAY_ZH = ["一", "二", "三", "四", "五", "六", "日"]


class DayKind(str, enum.Enum):
    """Editability / labor-law classification for a calendar day."""

    WORKDAY = "WORKDAY"
    MAKEUP_WORKDAY = "MAKEUP_WORKDAY"
    NATIONAL_HOLIDAY = "NATIONAL_HOLIDAY"
    REST_DAY = "REST_DAY"          # 休息日 — Saturday (non-makeup)
    REGULAR_LEAVE = "REGULAR_LEAVE"  # 例假日 — Sunday


def classify_day_kind(day: "DayInfo") -> DayKind:
    """Classify a DayInfo into a DayKind for editability + display.

    Rules (in order):
    - Sunday is always REGULAR_LEAVE — labor-law-mandated weekly rest; takes
      priority even if a national holiday also falls on this Sunday, because
      the editing lock is what matters to callers.
    - A makeup workday (補班) is treated as a normal workday, even on Saturday.
    - Saturday with is_holiday=True (and not makeup) is REST_DAY (休息日).
    - Any other is_holiday day (weekday) is NATIONAL_HOLIDAY.
    - Otherwise WORKDAY.
    """
    weekday = day.date.weekday()  # Mon=0 ... Sun=6
    if weekday == 6:
        return DayKind.REGULAR_LEAVE
    if day.is_makeup_workday:
        return DayKind.MAKEUP_WORKDAY
    if weekday == 5 and day.is_holiday:
        return DayKind.REST_DAY
    if day.is_holiday:
        return DayKind.NATIONAL_HOLIDAY
    return DayKind.WORKDAY

CALENDAR_CDN_URL = "https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json"


@dataclass(frozen=True)
class DayInfo:
    """Information about a single calendar day."""

    date: datetime.date
    weekday_zh: str
    is_holiday: bool
    description: str
    is_makeup_workday: bool


def parse_calendar_json(raw_entries: list[dict[str, Any]]) -> list[DayInfo]:
    """Parse raw JSON entries into DayInfo objects."""
    result: list[DayInfo] = []
    for entry in raw_entries:
        date_str = entry["date"]
        d = datetime.date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
        is_holiday = bool(entry["isHoliday"])
        description = entry.get("description", "")
        is_makeup = not is_holiday and any(kw in description for kw in _MAKEUP_KEYWORDS)
        weekday_zh = entry.get("week", _WEEKDAY_ZH[d.weekday()])
        result.append(
            DayInfo(
                date=d,
                weekday_zh=weekday_zh,
                is_holiday=is_holiday,
                description=description,
                is_makeup_workday=is_makeup,
            )
        )
    return result


def index_calendar(data: list[DayInfo]) -> dict[datetime.date, DayInfo]:
    """Build a date→DayInfo dict for O(1) lookups. Cheap; build once per year."""
    return {d.date: d for d in data}


def _weekday_fallback(target: datetime.date) -> DayKind:
    weekday = target.weekday()
    if weekday == 6:
        return DayKind.REGULAR_LEAVE
    if weekday == 5:
        return DayKind.REST_DAY
    return DayKind.WORKDAY


def classify_date_kind(data: list[DayInfo], target: datetime.date) -> DayKind:
    """Classify a date using parsed calendar data, with weekday fallback.

    O(n) list scan — use ``classify_indexed_date_kind`` when classifying many
    dates against the same calendar.
    """
    for day in data:
        if day.date == target:
            return classify_day_kind(day)
    return _weekday_fallback(target)


def classify_indexed_date_kind(
    index: dict[datetime.date, DayInfo], target: datetime.date
) -> DayKind:
    """O(1) classification using a pre-built index from ``index_calendar``."""
    day = index.get(target)
    return classify_day_kind(day) if day is not None else _weekday_fallback(target)


def is_workday_from_data(data: list[DayInfo], target: datetime.date) -> bool:
    """Check if a date is a workday using parsed calendar data.

    Falls back to Mon-Fri if date is not in the data.
    """
    for day in data:
        if day.date == target:
            return not day.is_holiday
    # Fallback: Mon(0)-Fri(4) = workday
    return target.weekday() < 5


def get_month_info_from_data(
    data: list[DayInfo], year: int, month: int
) -> list[DayInfo]:
    """Get DayInfo for every day in a month.

    Days missing from calendar data are filled with defaults
    (Mon-Fri = workday, Sat-Sun = holiday).
    """
    days_in_month = calendar.monthrange(year, month)[1]
    data_by_date = {day.date: day for day in data}

    result: list[DayInfo] = []
    for day_num in range(1, days_in_month + 1):
        d = datetime.date(year, month, day_num)
        if d in data_by_date:
            result.append(data_by_date[d])
        else:
            is_weekend = d.weekday() >= 5
            result.append(
                DayInfo(
                    date=d,
                    weekday_zh=_WEEKDAY_ZH[d.weekday()],
                    is_holiday=is_weekend,
                    description="",
                    is_makeup_workday=False,
                )
            )
    return result


async def fetch_calendar_from_cdn(year: int) -> list[DayInfo]:
    """Fetch Taiwan calendar data from ruyut/TaiwanCalendar CDN.

    Returns empty list on any failure (network, 404, parse error).
    """
    url = CALENDAR_CDN_URL.format(year=year)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
        if response.status_code != 200:
            return []
        return parse_calendar_json(response.json())
    except Exception:
        return []
