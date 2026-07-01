"""NFC door-tap import service — CP950 parsing + per-side gap-fill backup.

Reads a SOYAL 701 ``YYYYMM.txt`` export (CP950/Big5) and, for each
(emp_id, date), fills ONLY the missing side (clock-in / clock-out) of the day
from the door taps. A real phone punch always wins; NFC never displaces it.
Idempotent: a filled side is never re-filled, so re-importing the cumulative
monthly file is a no-op.
"""

import datetime
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance_log import AttendanceLog, WorkMode
from app.models.employee import Employee
from app.repositories import (
    attendance_repository,
    employee_repository,
    system_config_repository,
)
from app.services import reporting_service
from app.utils.taiwan_calendar import (
    DayInfo,
    classify_indexed_date_kind,
    index_calendar,
    parse_calendar_json,
)

CARD_ENCODING = "cp950"
NFC_IP_MARKER = "nfc"


@dataclass(frozen=True)
class NfcTap:
    """One decoded door-tap row."""

    emp_id: str
    timestamp: datetime.datetime
    door_no: str
    card_serial: str
    name: str


def decode_file(raw: bytes) -> str:
    """Decode CP950/Big5 bytes to text.

    ASCII fields (date/time/emp_id/door/serial) are single-byte and always
    safe; ``errors="replace"`` keeps one malformed name byte from killing the
    whole import (names are informational only).
    """
    return raw.decode(CARD_ENCODING, errors="replace")


def parse_rows(text: str) -> tuple[list[NfcTap], list[str]]:
    """Parse decoded CSV text into taps plus a list of malformed raw lines.

    Expected columns: ``date(YYYYMMDD), time(HHMMSS), emp_id, door_no,
    card_serial, name``. Blank lines are skipped silently.
    """
    taps: list[NfcTap] = []
    errors: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(",", 5)
        if len(parts) < 6:
            errors.append(raw_line)
            continue
        date_s, time_s, emp_id, door_no, card_serial, name = (p.strip() for p in parts)
        if not emp_id:
            errors.append(raw_line)
            continue
        try:
            ts = datetime.datetime.strptime(date_s + time_s, "%Y%m%d%H%M%S")
        except ValueError:
            errors.append(raw_line)
            continue
        taps.append(
            NfcTap(
                emp_id=emp_id,
                timestamp=ts,
                door_no=door_no,
                card_serial=card_serial,
                name=name,
            )
        )
    return taps, errors


@dataclass(frozen=True)
class NfcImportResult:
    """Immutable summary of one import run."""

    filled_in: int
    filled_out: int
    skipped_already_punched: int
    skipped_terminated: list[str]
    unknown_emp_ids: list[str]
    parse_errors: list[str]
    affected_days: list[str]


async def _load_calendar_index(
    session: AsyncSession, year: int
) -> dict[datetime.date, DayInfo]:
    """Cached Taiwan calendar as date→DayInfo for O(1) day_kind lookups.

    Cached-only (no CDN fetch) — mirrors attendance_service; a cold cache
    degrades to the pure weekday fallback inside classify_indexed_date_kind.
    """
    cached = await system_config_repository.get_workday_calendar(session, year)
    data = parse_calendar_json(cached.get("entries", [])) if cached else []
    return index_calendar(data)


def _group_by_emp_date(
    taps: list[NfcTap],
) -> dict[tuple[str, datetime.date], list[NfcTap]]:
    groups: dict[tuple[str, datetime.date], list[NfcTap]] = {}
    for tap in taps:
        groups.setdefault((tap.emp_id, tap.timestamp.date()), []).append(tap)
    return groups


def _make_nfc_log(emp_id: str, ts: datetime.datetime) -> AttendanceLog:
    return AttendanceLog(
        emp_id=emp_id,
        timestamp=ts,
        latitude=0.0,
        longitude=0.0,
        accuracy=0.0,
        ip_address=NFC_IP_MARKER,
        work_mode=WorkMode.OFFICE,
        is_overridden=False,
    )


async def import_nfc_file(session: AsyncSession, raw: bytes) -> NfcImportResult:
    """Decode, parse, and per-side gap-fill a SOYAL door-tap export."""
    taps, parse_errors = parse_rows(decode_file(raw))
    groups = _group_by_emp_date(taps)

    filled_in = 0
    filled_out = 0
    skipped_already_punched = 0
    skipped_terminated: list[str] = []
    unknown_emp_ids: list[str] = []
    affected_days: list[str] = []

    # Preload calendars for every touched year so summary regen gets the
    # calendar-accurate day_kind (補班 Saturdays, weekday holidays) without N+1.
    calendars = {
        year: await _load_calendar_index(session, year)
        for year in {date.year for (_emp, date) in groups}
    }
    employee_cache: dict[str, Employee | None] = {}

    for (emp_id, date), day_taps in sorted(
        groups.items(), key=lambda kv: (kv[0][1], kv[0][0])
    ):
        if emp_id not in employee_cache:
            employee_cache[emp_id] = await employee_repository.find_by_id(
                session, emp_id
            )
        employee = employee_cache[emp_id]
        if employee is None:
            if emp_id not in unknown_emp_ids:
                unknown_emp_ids.append(emp_id)
            continue
        if employee.terminated_at is not None and employee.terminated_at.date() <= date:
            if emp_id not in skipped_terminated:
                skipped_terminated.append(emp_id)
            continue

        existing = await attendance_repository.find_by_employee_and_date(
            session, emp_id, date
        )
        non_overridden = [log for log in existing if not log.is_overridden]
        has_in = len(non_overridden) >= 1
        has_out = len(non_overridden) >= 2

        if has_in and has_out:
            skipped_already_punched += 1
            continue

        day_taps.sort(key=lambda tap: tap.timestamp)
        earliest = day_taps[0].timestamp
        latest = day_taps[-1].timestamp
        did_fill = False

        if has_in:
            effective_in = min(log.timestamp for log in non_overridden)
        else:
            await attendance_repository.create_log(
                session, _make_nfc_log(emp_id, earliest)
            )
            filled_in += 1
            did_fill = True
            effective_in = earliest

        if not has_out and latest > effective_in:
            await attendance_repository.create_log(
                session, _make_nfc_log(emp_id, latest)
            )
            filled_out += 1
            did_fill = True

        if did_fill:
            day_kind = classify_indexed_date_kind(calendars[date.year], date)
            await reporting_service.generate_daily_summary(
                session, emp_id, date, day_kind=day_kind
            )
            affected_days.append(f"{emp_id} {date.isoformat()}")

    return NfcImportResult(
        filled_in=filled_in,
        filled_out=filled_out,
        skipped_already_punched=skipped_already_punched,
        skipped_terminated=skipped_terminated,
        unknown_emp_ids=unknown_emp_ids,
        parse_errors=parse_errors,
        affected_days=affected_days,
    )
