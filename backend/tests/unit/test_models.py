"""Unit tests for SQLModel database models — Phase 1C."""

import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select


# ---------- 1. Employee model fields ----------
async def test_employee_model_fields(db_session):
    from app.models.employee import Employee, Role

    emp = Employee(
        emp_id="EMP001",
        name="Alice Wang",
        department="Engineering",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw_placeholder",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()

    result = await db_session.execute(
        select(Employee).where(Employee.emp_id == "EMP001")
    )
    row = result.scalars().one()

    assert row.emp_id == "EMP001"
    assert row.name == "Alice Wang"
    assert row.department == "Engineering"
    assert row.role == Role.EMPLOYEE
    assert row.hashed_password == "hashed_pw_placeholder"
    assert row.shift_start_time == datetime.time(9, 0)
    assert row.shift_end_time == datetime.time(18, 0)


# ---------- 2. Employee role enum ----------
async def test_employee_role_enum(db_session):
    from app.models.employee import Role

    assert Role.EMPLOYEE.value == "EMPLOYEE"
    assert Role.MANAGER.value == "MANAGER"
    assert Role.HR.value == "HR"
    assert Role.ADMIN.value == "ADMIN"

    # Exactly 4 members
    assert len(Role) == 4

    # Invalid value should not be in the enum
    with pytest.raises(ValueError):
        Role("INVALID_ROLE")


# ---------- 3. Authenticator model fields ----------
async def test_authenticator_model_fields(db_session):
    from app.models.authenticator import Authenticator
    from app.models.employee import Employee, Role

    emp = Employee(
        emp_id="EMP002",
        name="Bob Lin",
        department="HR",
        role=Role.HR,
        hashed_password="hashed_pw",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()

    auth = Authenticator(
        credential_id="cred_abc123",
        emp_id="EMP002",
        public_key=b"\x01\x02\x03",
        sign_count=0,
    )
    db_session.add(auth)
    await db_session.commit()

    result = await db_session.execute(
        select(Authenticator).where(Authenticator.credential_id == "cred_abc123")
    )
    row = result.scalars().one()

    assert row.credential_id == "cred_abc123"
    assert row.emp_id == "EMP002"
    assert row.public_key == b"\x01\x02\x03"
    assert row.sign_count == 0


# ---------- 4. AttendanceLog model fields ----------
async def test_attendance_log_model_fields(db_session):
    from app.models.attendance_log import AttendanceLog, WorkMode
    from app.models.employee import Employee, Role

    emp = Employee(
        emp_id="EMP003",
        name="Carol Chen",
        department="Sales",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()

    now = datetime.datetime(2026, 3, 19, 9, 0, 0)
    log = AttendanceLog(
        emp_id="EMP003",
        timestamp=now,
        latitude=25.033,
        longitude=121.565,
        accuracy=10.5,
        ip_address="192.168.1.1",
        work_mode=WorkMode.OFFICE,
    )
    db_session.add(log)
    await db_session.commit()

    result = await db_session.execute(
        select(AttendanceLog).where(AttendanceLog.emp_id == "EMP003")
    )
    row = result.scalars().one()

    assert row.id is not None  # auto-increment PK
    assert row.emp_id == "EMP003"
    assert row.timestamp == now
    assert row.latitude == pytest.approx(25.033)
    assert row.longitude == pytest.approx(121.565)
    assert row.accuracy == pytest.approx(10.5)
    assert row.ip_address == "192.168.1.1"
    assert row.work_mode == WorkMode.OFFICE
    assert row.is_overridden is False  # default


# ---------- 5. AttendanceLog immutability design ----------
async def test_attendance_log_immutability_design(db_session):
    """Verify attendance logs can be created as an append-only event stream.

    Immutability is enforced at the repository/service level, not the model
    level. Here we just confirm the model supports creating log entries.
    """
    from app.models.attendance_log import AttendanceLog, WorkMode
    from app.models.employee import Employee, Role

    emp = Employee(
        emp_id="EMP004",
        name="Dan Wu",
        department="Ops",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw",
        shift_start_time=datetime.time(8, 0),
        shift_end_time=datetime.time(17, 0),
    )
    db_session.add(emp)
    await db_session.commit()

    ts1 = datetime.datetime(2026, 3, 19, 8, 0, 0)
    ts2 = datetime.datetime(2026, 3, 19, 17, 0, 0)

    log1 = AttendanceLog(
        emp_id="EMP004",
        timestamp=ts1,
        latitude=25.0,
        longitude=121.5,
        accuracy=5.0,
        ip_address="10.0.0.1",
        work_mode=WorkMode.OFFICE,
    )
    log2 = AttendanceLog(
        emp_id="EMP004",
        timestamp=ts2,
        latitude=25.0,
        longitude=121.5,
        accuracy=5.0,
        ip_address="10.0.0.1",
        work_mode=WorkMode.WFH,
    )
    db_session.add_all([log1, log2])
    await db_session.commit()

    result = await db_session.execute(
        select(AttendanceLog).where(AttendanceLog.emp_id == "EMP004")
    )
    rows = result.scalars().all()
    assert len(rows) == 2


# ---------- 6. SystemConfig model fields ----------
async def test_system_config_model_fields(db_session):
    from app.models.system_config import SystemConfig

    config = SystemConfig(
        key="office_location",
        value={"lat": 25.033, "lng": 121.565, "radius_m": 200},
        updated_by=None,
        updated_at=datetime.datetime(2026, 3, 19, 12, 0, 0),
    )
    db_session.add(config)
    await db_session.commit()

    result = await db_session.execute(
        select(SystemConfig).where(SystemConfig.key == "office_location")
    )
    row = result.scalars().one()

    assert row.key == "office_location"
    assert row.value == {"lat": 25.033, "lng": 121.565, "radius_m": 200}
    assert row.updated_by is None
    assert row.updated_at == datetime.datetime(2026, 3, 19, 12, 0, 0)


# ---------- 7. DailyAttendanceSummary model fields ----------
async def test_daily_attendance_summary_fields(db_session):
    from app.models.daily_attendance_summary import (
        AttendanceStatus,
        DailyAttendanceSummary,
    )
    from app.models.employee import Employee, Role

    emp = Employee(
        emp_id="EMP005",
        name="Eve Hsu",
        department="Finance",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()

    summary = DailyAttendanceSummary(
        emp_id="EMP005",
        date=datetime.date(2026, 3, 19),
        first_clock_in=datetime.datetime(2026, 3, 19, 9, 5, 0),
        last_clock_out=datetime.datetime(2026, 3, 19, 18, 10, 0),
        status=AttendanceStatus.NORMAL,
    )
    db_session.add(summary)
    await db_session.commit()

    result = await db_session.execute(
        select(DailyAttendanceSummary).where(
            DailyAttendanceSummary.emp_id == "EMP005"
        )
    )
    row = result.scalars().one()

    assert row.id is not None
    assert row.emp_id == "EMP005"
    assert row.date == datetime.date(2026, 3, 19)
    assert row.first_clock_in == datetime.datetime(2026, 3, 19, 9, 5, 0)
    assert row.last_clock_out == datetime.datetime(2026, 3, 19, 18, 10, 0)
    assert row.status == AttendanceStatus.NORMAL

    # Verify all status enum members
    assert AttendanceStatus.NORMAL.value == "NORMAL"
    assert AttendanceStatus.LATE.value == "LATE"
    assert AttendanceStatus.EARLY_LEAVE.value == "EARLY_LEAVE"
    assert AttendanceStatus.LATE_AND_EARLY_LEAVE.value == "LATE_AND_EARLY_LEAVE"
    assert AttendanceStatus.ABNORMAL.value == "ABNORMAL"
    assert len(AttendanceStatus) == 5


# ---------- 8. Employee -> Authenticator relationship (via FK) ----------
async def test_employee_authenticator_relationship(db_session):
    from app.models.authenticator import Authenticator
    from app.models.employee import Employee, Role

    emp = Employee(
        emp_id="EMP006",
        name="Frank Liu",
        department="IT",
        role=Role.ADMIN,
        hashed_password="hashed_pw",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()

    auth1 = Authenticator(
        credential_id="cred_001",
        emp_id="EMP006",
        public_key=b"\xaa\xbb",
        sign_count=0,
    )
    auth2 = Authenticator(
        credential_id="cred_002",
        emp_id="EMP006",
        public_key=b"\xcc\xdd",
        sign_count=1,
    )
    db_session.add_all([auth1, auth2])
    await db_session.commit()

    result = await db_session.execute(
        select(Authenticator).where(Authenticator.emp_id == "EMP006")
    )
    rows = result.scalars().all()
    assert len(rows) == 2
    assert all(r.emp_id == "EMP006" for r in rows)


# ---------- 9. Employee -> AttendanceLog relationship (via FK) ----------
async def test_employee_attendance_relationship(db_session):
    from app.models.attendance_log import AttendanceLog, WorkMode
    from app.models.employee import Employee, Role

    emp = Employee(
        emp_id="EMP007",
        name="Grace Tsai",
        department="Marketing",
        role=Role.MANAGER,
        hashed_password="hashed_pw",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()

    for i in range(3):
        log = AttendanceLog(
            emp_id="EMP007",
            timestamp=datetime.datetime(2026, 3, 19, 9 + i, 0, 0),
            latitude=25.0,
            longitude=121.5,
            accuracy=5.0,
            ip_address="10.0.0.1",
            work_mode=WorkMode.OFFICE,
        )
        db_session.add(log)
    await db_session.commit()

    result = await db_session.execute(
        select(AttendanceLog).where(AttendanceLog.emp_id == "EMP007")
    )
    rows = result.scalars().all()
    assert len(rows) == 3
    assert all(r.emp_id == "EMP007" for r in rows)


# ---------- 10. Unique constraint on (emp_id, date) ----------
async def test_unique_summary_per_employee_per_date(db_session):
    from app.models.daily_attendance_summary import (
        AttendanceStatus,
        DailyAttendanceSummary,
    )
    from app.models.employee import Employee, Role

    emp = Employee(
        emp_id="EMP008",
        name="Henry Chang",
        department="Ops",
        role=Role.EMPLOYEE,
        hashed_password="hashed_pw",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    db_session.add(emp)
    await db_session.commit()

    summary1 = DailyAttendanceSummary(
        emp_id="EMP008",
        date=datetime.date(2026, 3, 19),
        first_clock_in=datetime.datetime(2026, 3, 19, 9, 0, 0),
        last_clock_out=datetime.datetime(2026, 3, 19, 18, 0, 0),
        status=AttendanceStatus.NORMAL,
    )
    db_session.add(summary1)
    await db_session.commit()

    # Duplicate (emp_id, date) should raise IntegrityError
    summary2 = DailyAttendanceSummary(
        emp_id="EMP008",
        date=datetime.date(2026, 3, 19),
        first_clock_in=datetime.datetime(2026, 3, 19, 9, 30, 0),
        last_clock_out=datetime.datetime(2026, 3, 19, 17, 30, 0),
        status=AttendanceStatus.LATE,
    )
    db_session.add(summary2)

    with pytest.raises(IntegrityError):
        await db_session.commit()
