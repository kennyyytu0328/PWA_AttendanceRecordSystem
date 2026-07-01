"""Unit tests for the NFC door-tap import service."""

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.daily_attendance_summary import AttendanceStatus
from app.models.employee import Employee, Role
from app.repositories import attendance_repository, summary_repository


def _make_employee(
    emp_id: str = "F1000118",
    role: Role = Role.EMPLOYEE,
    terminated_at: datetime.datetime | None = None,
) -> Employee:
    return Employee(
        emp_id=emp_id,
        name="Test User",
        department="Engineering",
        role=role,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
        terminated_at=terminated_at,
    )


def _cp950(rows: list[str]) -> bytes:
    """Encode CSV rows as a CP950/Big5 file body (as SOYAL exports them)."""
    return ("\n".join(rows) + "\n").encode("cp950")


def test_decode_file_cp950_round_trips_chinese_name():
    from app.services.nfc_import_service import decode_file

    raw = _cp950(["20260701,072437,F1000118,1,5717003342,王小明"])
    text = decode_file(raw)
    assert "王小明" in text
    assert "F1000118" in text


def test_parse_rows_valid():
    from app.services.nfc_import_service import parse_rows

    text = (
        "20260701,072437,F1000118,1,5717003342,王小明\n"
        "20260701,181045,F1000118,2,5717003342,王小明\n"
    )
    taps, errors = parse_rows(text)
    assert errors == []
    assert len(taps) == 2
    assert taps[0].emp_id == "F1000118"
    assert taps[0].timestamp == datetime.datetime(2026, 7, 1, 7, 24, 37)
    assert taps[0].door_no == "1"
    assert taps[0].card_serial == "5717003342"
    assert taps[1].timestamp == datetime.datetime(2026, 7, 1, 18, 10, 45)


def test_parse_rows_collects_malformed_lines():
    from app.services.nfc_import_service import parse_rows

    text = (
        "20260701,072437,F1000118,1,5717003342,王小明\n"
        "not,enough,fields\n"                              # too few columns
        "20261301,072437,F1000220,1,6108331019,李四\n"     # month 13 → bad date
        "\n"                                               # blank → skipped, no error
    )
    taps, errors = parse_rows(text)
    assert len(taps) == 1
    assert taps[0].emp_id == "F1000118"
    assert len(errors) == 2
