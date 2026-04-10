"""Taiwan workday calendar utility.

Parses calendar JSON from ruyut/TaiwanCalendar (sourced from 行政院人事行政總處).
Data URL: https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json
"""

from __future__ import annotations

import calendar
import datetime
from dataclasses import dataclass
from typing import Any

_MAKEUP_KEYWORDS = ("補行上班", "補班")
_WEEKDAY_ZH = ["一", "二", "三", "四", "五", "六", "日"]

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
