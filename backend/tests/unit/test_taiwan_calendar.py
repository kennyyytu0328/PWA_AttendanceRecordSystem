"""Tests for Taiwan workday calendar utility."""

import datetime

import pytest

from app.utils.taiwan_calendar import DayInfo, parse_calendar_json, get_month_info_from_data, is_workday_from_data


# --- Test data ---

_SAMPLE_CALENDAR: list[dict] = [
    {"date": "20260101", "week": "四", "isHoliday": True, "description": "中華民國開國紀念日"},
    {"date": "20260102", "week": "五", "isHoliday": False, "description": ""},
    {"date": "20260103", "week": "六", "isHoliday": True, "description": ""},
    {"date": "20260104", "week": "日", "isHoliday": True, "description": ""},
    {"date": "20260105", "week": "一", "isHoliday": False, "description": ""},
    {"date": "20260131", "week": "六", "isHoliday": False, "description": "補行上班"},
]


class TestParsing:
    def test_parse_calendar_json_returns_list_of_day_info(self):
        result = parse_calendar_json(_SAMPLE_CALENDAR)
        assert len(result) == 6
        assert isinstance(result[0], DayInfo)

    def test_parse_holiday_entry(self):
        result = parse_calendar_json(_SAMPLE_CALENDAR)
        day = result[0]  # 2026-01-01
        assert day.date == datetime.date(2026, 1, 1)
        assert day.is_holiday is True
        assert day.description == "中華民國開國紀念日"
        assert day.weekday_zh == "四"

    def test_parse_workday_entry(self):
        result = parse_calendar_json(_SAMPLE_CALENDAR)
        day = result[1]  # 2026-01-02
        assert day.date == datetime.date(2026, 1, 2)
        assert day.is_holiday is False
        assert day.description == ""

    def test_parse_makeup_workday(self):
        result = parse_calendar_json(_SAMPLE_CALENDAR)
        day = result[5]  # 2026-01-31, 補行上班
        assert day.is_holiday is False
        assert day.is_makeup_workday is True
        assert day.description == "補行上班"

    def test_weekend_without_description_is_not_makeup(self):
        result = parse_calendar_json(_SAMPLE_CALENDAR)
        day = result[2]  # 2026-01-03, Saturday holiday
        assert day.is_holiday is True
        assert day.is_makeup_workday is False


class TestIsWorkday:
    def test_regular_workday(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        assert is_workday_from_data(data, datetime.date(2026, 1, 2)) is True

    def test_national_holiday(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        assert is_workday_from_data(data, datetime.date(2026, 1, 1)) is False

    def test_weekend_is_not_workday(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        assert is_workday_from_data(data, datetime.date(2026, 1, 3)) is False

    def test_makeup_workday_is_workday(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        assert is_workday_from_data(data, datetime.date(2026, 1, 31)) is True

    def test_date_not_in_data_weekday_fallback(self):
        """Dates not in calendar data fall back to Mon-Fri = workday."""
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        # 2026-03-02 is Monday, not in sample data
        assert is_workday_from_data(data, datetime.date(2026, 3, 2)) is True

    def test_date_not_in_data_weekend_fallback(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        # 2026-03-07 is Saturday, not in sample data
        assert is_workday_from_data(data, datetime.date(2026, 3, 7)) is False


class TestGetMonthInfo:
    def test_returns_all_days_in_month(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        result = get_month_info_from_data(data, 2026, 1)
        assert len(result) == 31  # January has 31 days

    def test_fills_missing_days_with_defaults(self):
        data = parse_calendar_json(_SAMPLE_CALENDAR)
        result = get_month_info_from_data(data, 2026, 1)
        # 2026-01-06 is Tuesday, not in sample → default workday
        day_06 = next(d for d in result if d.date == datetime.date(2026, 1, 6))
        assert day_06.is_holiday is False
        assert day_06.description == ""

    def test_february_leap_year(self):
        data = parse_calendar_json([])
        result = get_month_info_from_data(data, 2028, 2)
        assert len(result) == 29  # 2028 is leap year

    def test_february_non_leap_year(self):
        data = parse_calendar_json([])
        result = get_month_info_from_data(data, 2026, 2)
        assert len(result) == 28
