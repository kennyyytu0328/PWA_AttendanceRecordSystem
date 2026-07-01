"""Pydantic schema for the NFC import endpoint response."""

from pydantic import BaseModel


class NfcImportResponse(BaseModel):
    """Report returned by POST /api/nfc/import."""

    filled_in: int
    filled_out: int
    skipped_already_punched: int
    skipped_terminated: list[str]
    unknown_emp_ids: list[str]
    parse_errors: list[str]
    affected_days: list[str]
