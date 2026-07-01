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


async def _non_overridden(db_session: AsyncSession, emp_id: str, date: datetime.date):
    logs = await attendance_repository.find_by_employee_and_date(db_session, emp_id, date)
    return [l for l in logs if not l.is_overridden]


@pytest.mark.asyncio
async def test_import_whole_day_empty_fills_both(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    await db_session.commit()

    raw = _cp950([
        "20260701,072437,F1000118,1,5717003342,王小明",
        "20260701,181045,F1000118,2,5717003342,王小明",
    ])
    result = await import_nfc_file(db_session, raw)

    assert result.filled_in == 1
    assert result.filled_out == 1
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert len(logs) == 2
    assert all(l.ip_address == "nfc" for l in logs)
    assert {l.timestamp.time() for l in logs} == {
        datetime.time(7, 24, 37), datetime.time(18, 10, 45),
    }


@pytest.mark.asyncio
async def test_import_single_tap_fills_in_only(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    await db_session.commit()

    raw = _cp950(["20260701,072437,F1000118,1,5717003342,王小明"])
    result = await import_nfc_file(db_session, raw)

    assert result.filled_in == 1
    assert result.filled_out == 0
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_import_fills_missing_out_keeps_phone_in(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    db_session.add(AttendanceLog(
        emp_id="F1000118",
        timestamp=datetime.datetime(2026, 7, 1, 8, 53, 0),
        latitude=25.0, longitude=121.0, accuracy=10.0,
        ip_address="127.0.0.1", work_mode=WorkMode.OFFICE, is_overridden=False,
    ))
    await db_session.commit()

    raw = _cp950(["20260701,181045,F1000118,2,5717003342,王小明"])
    result = await import_nfc_file(db_session, raw)

    assert result.filled_in == 0
    assert result.filled_out == 1
    first = await attendance_repository.find_first_clock_in(
        db_session, "F1000118", datetime.date(2026, 7, 1))
    last = await attendance_repository.find_last_clock_out(
        db_session, "F1000118", datetime.date(2026, 7, 1))
    assert first.timestamp.time() == datetime.time(8, 53)   # phone in preserved
    assert last.timestamp.time() == datetime.time(18, 10, 45)  # nfc out


@pytest.mark.asyncio
async def test_import_does_not_displace_phone_with_earlier_tap(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    db_session.add(AttendanceLog(
        emp_id="F1000118",
        timestamp=datetime.datetime(2026, 7, 1, 8, 53, 0),
        latitude=25.0, longitude=121.0, accuracy=10.0,
        ip_address="127.0.0.1", work_mode=WorkMode.OFFICE, is_overridden=False,
    ))
    await db_session.commit()

    # Only an EARLIER tap exists — cannot become a clock-out (guard: > clock-in).
    raw = _cp950(["20260701,072437,F1000118,1,5717003342,王小明"])
    result = await import_nfc_file(db_session, raw)

    assert result.filled_in == 0
    assert result.filled_out == 0
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_import_complete_day_is_noop(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    for t in (datetime.datetime(2026, 7, 1, 8, 53), datetime.datetime(2026, 7, 1, 18, 2)):
        db_session.add(AttendanceLog(
            emp_id="F1000118", timestamp=t, latitude=25.0, longitude=121.0,
            accuracy=10.0, ip_address="127.0.0.1", work_mode=WorkMode.OFFICE,
            is_overridden=False,
        ))
    await db_session.commit()

    raw = _cp950([
        "20260701,072437,F1000118,1,5717003342,王小明",
        "20260701,190000,F1000118,2,5717003342,王小明",
    ])
    result = await import_nfc_file(db_session, raw)

    assert result.filled_in == 0
    assert result.filled_out == 0
    assert result.skipped_already_punched == 1
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert len(logs) == 2  # unchanged


@pytest.mark.asyncio
async def test_import_is_idempotent(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    await db_session.commit()

    raw = _cp950([
        "20260701,072437,F1000118,1,5717003342,王小明",
        "20260701,181045,F1000118,2,5717003342,王小明",
    ])
    await import_nfc_file(db_session, raw)
    second = await import_nfc_file(db_session, raw)

    assert second.filled_in == 0
    assert second.filled_out == 0
    assert second.skipped_already_punched == 1
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert len(logs) == 2  # no duplicates


@pytest.mark.asyncio
async def test_import_unknown_emp_id_is_reported_not_fatal(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee("F1000118"))
    await db_session.commit()

    raw = _cp950([
        "20260701,072437,F1000118,1,5717003342,王小明",
        "20260701,073000,GHOST999,1,9999999999,幽靈",
    ])
    result = await import_nfc_file(db_session, raw)

    assert result.unknown_emp_ids == ["GHOST999"]
    assert result.filled_in == 1  # the real employee still filled
    ghost = await _non_overridden(db_session, "GHOST999", datetime.date(2026, 7, 1))
    assert ghost == []


@pytest.mark.asyncio
async def test_import_skips_terminated_employee(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee(
        "F1000118", terminated_at=datetime.datetime(2026, 6, 1)))
    await db_session.commit()

    raw = _cp950(["20260701,072437,F1000118,1,5717003342,王小明"])
    result = await import_nfc_file(db_session, raw)

    assert result.skipped_terminated == ["F1000118"]
    assert result.filled_in == 0
    logs = await _non_overridden(db_session, "F1000118", datetime.date(2026, 7, 1))
    assert logs == []


@pytest.mark.asyncio
async def test_import_weekend_tap_scores_normal(db_session: AsyncSession):
    from app.services.nfc_import_service import import_nfc_file

    db_session.add(_make_employee())
    await db_session.commit()

    sunday = datetime.date(2026, 7, 5)
    assert sunday.weekday() == 6  # Sunday → 例假日 → NORMAL, not LATE/EARLY
    raw = _cp950([
        "20260705,100000,F1000118,1,5717003342,王小明",
        "20260705,140000,F1000118,2,5717003342,王小明",
    ])
    await import_nfc_file(db_session, raw)

    summaries = await summary_repository.find_by_employee(
        db_session, "F1000118", start_date=sunday, end_date=sunday)
    assert len(summaries) == 1
    assert summaries[0].status == AttendanceStatus.NORMAL
