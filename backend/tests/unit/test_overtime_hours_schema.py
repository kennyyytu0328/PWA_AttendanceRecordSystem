"""Tests for BulkOverrideEntry.overtime_hours validation."""

import datetime
import decimal

import pytest
from pydantic import ValidationError

from app.schemas.bulk_override import BulkOverrideEntry


class TestOvertimeHoursValidation:
    def test_none_is_allowed(self):
        entry = BulkOverrideEntry(date=datetime.date(2026, 1, 5), overtime_hours=None)
        assert entry.overtime_hours is None

    @pytest.mark.parametrize("value", ["1.0", "1.5", "2.0", "2.5", "8.0", "8.5"])
    def test_valid_increments(self, value):
        entry = BulkOverrideEntry(
            date=datetime.date(2026, 1, 5),
            overtime_hours=decimal.Decimal(value),
        )
        assert entry.overtime_hours == decimal.Decimal(value)

    def test_first_half_hour_rejected(self):
        # 0.5 is below the 1.0 minimum — first hour must be a full hour.
        with pytest.raises(ValidationError):
            BulkOverrideEntry(
                date=datetime.date(2026, 1, 5),
                overtime_hours=decimal.Decimal("0.5"),
            )

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            BulkOverrideEntry(
                date=datetime.date(2026, 1, 5),
                overtime_hours=decimal.Decimal("-1.0"),
            )

    @pytest.mark.parametrize("value", ["1.3", "2.7", "1.25"])
    def test_non_half_hour_step_rejected(self, value):
        with pytest.raises(ValidationError):
            BulkOverrideEntry(
                date=datetime.date(2026, 1, 5),
                overtime_hours=decimal.Decimal(value),
            )
