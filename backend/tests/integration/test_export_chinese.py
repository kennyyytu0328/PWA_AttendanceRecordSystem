"""Tests for Chinese-ized export with new columns + submission filter."""
import csv
import datetime
import io

from app.models.daily_attendance_summary import AttendanceStatus
from app.models.employee import Employee, Role
from app.repositories import (
    monthly_submission_repository,
    summary_repository,
)
from app.services import reporting_service


async def _seed_employee_with_shift(
    session,
    emp_id: str,
    *,
    name: str = "Test User",
    department: str = "Eng",
    shift_start_time: str = "09:00",
    shift_end_time: str = "18:00",
) -> Employee:
    """Insert an employee with the given shift window (HH:MM strings)."""
    start_h, start_m = (int(p) for p in shift_start_time.split(":"))
    end_h, end_m = (int(p) for p in shift_end_time.split(":"))
    emp = Employee(
        emp_id=emp_id,
        name=name,
        department=department,
        role=Role.EMPLOYEE,
        hashed_password="x",
        shift_start_time=datetime.time(start_h, start_m),
        shift_end_time=datetime.time(end_h, end_m),
    )
    session.add(emp)
    await session.commit()
    await session.refresh(emp)
    return emp


async def test_csv_export_uses_chinese_headers(db_session):
    await _seed_employee_with_shift(
        db_session, emp_id="E040", shift_start_time="09:00", shift_end_time="18:00"
    )
    await summary_repository.upsert_summary(
        db_session,
        emp_id="E040",
        date=datetime.date(2026, 5, 14),
        first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        status=AttendanceStatus.NORMAL,
    )
    await monthly_submission_repository.upsert(
        db_session, emp_id="E040", year=2026, month=5
    )

    csv_text = await reporting_service.export_attendance(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        end_date=datetime.date(2026, 5, 14),
        format="csv",
    )
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    assert header == [
        "員工編號", "姓名", "部門", "日期",
        "班別時間", "上班時間", "下班時間",
        "狀態", "備註", "遲到理由", "送單狀態",
    ]


async def test_csv_export_translates_status_values(db_session):
    await _seed_employee_with_shift(
        db_session, emp_id="E041", shift_start_time="09:00", shift_end_time="18:00"
    )
    await summary_repository.upsert_summary(
        db_session,
        emp_id="E041",
        date=datetime.date(2026, 5, 14),
        first_clock_in=None,
        last_clock_out=None,
        status=AttendanceStatus.LEAVE,
        leave_type="特休",
        remark="上午",
    )
    await monthly_submission_repository.upsert(
        db_session, emp_id="E041", year=2026, month=5
    )

    csv_text = await reporting_service.export_attendance(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        end_date=datetime.date(2026, 5, 14),
        format="csv",
    )
    rows = list(csv.reader(io.StringIO(csv_text)))
    data_row = rows[1]
    assert data_row[0] == "E041"        # 員工編號
    assert data_row[7] == "請假"          # 狀態
    assert data_row[8] == "特休·上午"     # 備註
    assert data_row[10] == "已送單"       # 送單狀態


async def test_csv_export_default_excludes_unsubmitted(db_session):
    await _seed_employee_with_shift(
        db_session, emp_id="E042", shift_start_time="09:00", shift_end_time="18:00"
    )
    await summary_repository.upsert_summary(
        db_session,
        emp_id="E042",
        date=datetime.date(2026, 5, 14),
        first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        status=AttendanceStatus.NORMAL,
    )
    # NO submission for E042

    csv_text = await reporting_service.export_attendance(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        end_date=datetime.date(2026, 5, 14),
        format="csv",
    )
    assert "E042" not in csv_text


async def test_json_export_keeps_english(db_session):
    await _seed_employee_with_shift(
        db_session, emp_id="E043", shift_start_time="09:00", shift_end_time="18:00"
    )
    await summary_repository.upsert_summary(
        db_session,
        emp_id="E043",
        date=datetime.date(2026, 5, 14),
        first_clock_in=datetime.datetime(2026, 5, 14, 9, 0),
        last_clock_out=datetime.datetime(2026, 5, 14, 18, 0),
        status=AttendanceStatus.NORMAL,
    )
    await monthly_submission_repository.upsert(
        db_session, emp_id="E043", year=2026, month=5
    )

    json_text = await reporting_service.export_attendance(
        db_session,
        start_date=datetime.date(2026, 5, 14),
        end_date=datetime.date(2026, 5, 14),
        format="json",
    )
    assert '"emp_id"' in json_text
    assert '"status": "NORMAL"' in json_text
    assert '"shift_time"' in json_text
    assert '"remark"' in json_text
    assert '"submission_status"' in json_text
