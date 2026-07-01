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
