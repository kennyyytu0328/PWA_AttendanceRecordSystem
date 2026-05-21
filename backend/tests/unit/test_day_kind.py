"""Tests for the DayKind classifier (rest day / regular leave rules)."""

import datetime

from app.utils.taiwan_calendar import (
    DayInfo,
    DayKind,
    classify_date_kind,
    classify_day_kind,
)


def _day(date: datetime.date, *, holiday: bool = False, makeup: bool = False, desc: str = "") -> DayInfo:
    weekday_zh = "一二三四五六日"[date.weekday()]
    return DayInfo(
        date=date,
        weekday_zh=weekday_zh,
        is_holiday=holiday,
        description=desc,
        is_makeup_workday=makeup,
    )


class TestClassifyDayKind:
    def test_sunday_is_regular_leave(self):
        # 2026-01-04 is Sunday
        assert classify_day_kind(_day(datetime.date(2026, 1, 4), holiday=True)) == DayKind.REGULAR_LEAVE

    def test_sunday_overrides_national_holiday_label(self):
        # Even a Sunday tagged as a national holiday locks as REGULAR_LEAVE.
        assert classify_day_kind(
            _day(datetime.date(2026, 1, 4), holiday=True, desc="假設國定假日")
        ) == DayKind.REGULAR_LEAVE

    def test_saturday_non_makeup_is_rest_day(self):
        # 2026-01-03 is Saturday
        assert classify_day_kind(_day(datetime.date(2026, 1, 3), holiday=True)) == DayKind.REST_DAY

    def test_saturday_makeup_is_workday(self):
        # 2026-01-31 補班 Sat → MAKEUP_WORKDAY
        assert classify_day_kind(
            _day(datetime.date(2026, 1, 31), holiday=False, makeup=True, desc="補行上班")
        ) == DayKind.MAKEUP_WORKDAY

    def test_weekday_holiday_is_national_holiday(self):
        # 2026-01-01 (Thu) 元旦
        assert classify_day_kind(
            _day(datetime.date(2026, 1, 1), holiday=True, desc="中華民國開國紀念日")
        ) == DayKind.NATIONAL_HOLIDAY

    def test_regular_weekday_is_workday(self):
        # 2026-01-02 (Fri)
        assert classify_day_kind(_day(datetime.date(2026, 1, 2))) == DayKind.WORKDAY


class TestClassifyDateKindFallback:
    def test_fallback_sunday(self):
        assert classify_date_kind([], datetime.date(2026, 1, 4)) == DayKind.REGULAR_LEAVE

    def test_fallback_saturday(self):
        assert classify_date_kind([], datetime.date(2026, 1, 3)) == DayKind.REST_DAY

    def test_fallback_weekday(self):
        assert classify_date_kind([], datetime.date(2026, 1, 2)) == DayKind.WORKDAY

    def test_cached_overrides_fallback(self):
        # Saturday with explicit makeup beats the weekday-based fallback.
        data = [_day(datetime.date(2026, 1, 31), holiday=False, makeup=True, desc="補行上班")]
        assert classify_date_kind(data, datetime.date(2026, 1, 31)) == DayKind.MAKEUP_WORKDAY
