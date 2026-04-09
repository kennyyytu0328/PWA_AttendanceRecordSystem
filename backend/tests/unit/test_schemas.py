"""Unit tests for Pydantic schemas — Phase 1D."""

import datetime

import pytest
from pydantic import ValidationError


# ---------- 1. EmployeeCreate valid input ----------
def test_employee_create_schema_valid():
    from app.schemas.employee import EmployeeCreate

    data = EmployeeCreate(
        emp_id="EMP001",
        name="Alice Wang",
        department="Engineering",
        role="EMPLOYEE",
        password="secureP@ss1",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )

    assert data.emp_id == "EMP001"
    assert data.name == "Alice Wang"
    assert data.department == "Engineering"
    assert data.role.value == "EMPLOYEE"
    assert data.password == "secureP@ss1"
    assert data.shift_start_time == datetime.time(9, 0)
    assert data.shift_end_time == datetime.time(18, 0)


# ---------- 2. EmployeeCreate invalid role ----------
def test_employee_create_schema_invalid_role():
    from app.schemas.employee import EmployeeCreate

    with pytest.raises(ValidationError):
        EmployeeCreate(
            emp_id="EMP002",
            name="Bob Lin",
            department="HR",
            role="SUPERADMIN",
            password="secureP@ss2",
            shift_start_time=datetime.time(9, 0),
            shift_end_time=datetime.time(18, 0),
        )


# ---------- 3. EmployeeCreate missing fields ----------
def test_employee_create_schema_missing_fields():
    from app.schemas.employee import EmployeeCreate

    with pytest.raises(ValidationError):
        EmployeeCreate(
            emp_id="EMP003",
            # name is missing
            department="Sales",
            role="EMPLOYEE",
            password="secureP@ss3",
            shift_start_time=datetime.time(9, 0),
            shift_end_time=datetime.time(18, 0),
        )


# ---------- 4. PunchRequest valid input ----------
def test_attendance_log_schema_valid():
    from app.schemas.attendance import PunchRequest

    data = PunchRequest(
        latitude=25.033,
        longitude=121.565,
        accuracy=10.5,
        webauthn_response={"id": "cred_abc", "response": {}},
    )

    assert data.latitude == pytest.approx(25.033)
    assert data.longitude == pytest.approx(121.565)
    assert data.accuracy == pytest.approx(10.5)
    assert data.webauthn_response == {"id": "cred_abc", "response": {}}


# ---------- 5. PunchRequest invalid latitude ----------
def test_attendance_log_schema_invalid_latitude():
    from app.schemas.attendance import PunchRequest

    with pytest.raises(ValidationError):
        PunchRequest(
            latitude=91.0,
            longitude=121.565,
            accuracy=10.5,
            webauthn_response={"id": "cred_abc", "response": {}},
        )

    with pytest.raises(ValidationError):
        PunchRequest(
            latitude=-91.0,
            longitude=121.565,
            accuracy=10.5,
            webauthn_response={"id": "cred_abc", "response": {}},
        )


# ---------- 6. SystemConfigUpdate valid input ----------
def test_system_config_schema_valid():
    from app.schemas.system_config import SystemConfigUpdate

    data = SystemConfigUpdate(
        key="office_location",
        value={"lat": 25.033, "lng": 121.565, "radius_m": 200},
    )

    assert data.key == "office_location"
    assert data.value == {"lat": 25.033, "lng": 121.565, "radius_m": 200}


# ---------- 7. EmployeeResponse excludes password ----------
def test_employee_response_excludes_password():
    from app.schemas.employee import EmployeeResponse

    fields = EmployeeResponse.model_fields
    assert "hashed_password" not in fields
    assert "password" not in fields

    # Verify it can be constructed with expected fields
    resp = EmployeeResponse(
        emp_id="EMP001",
        name="Alice Wang",
        department="Engineering",
        role="EMPLOYEE",
        shift_start_time=datetime.time(9, 0),
        shift_end_time=datetime.time(18, 0),
    )
    assert resp.emp_id == "EMP001"
    assert not hasattr(resp, "hashed_password")
