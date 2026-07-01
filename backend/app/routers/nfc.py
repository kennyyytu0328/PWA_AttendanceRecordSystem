"""NFC door-tap import router — machine-to-machine, API-key authenticated."""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.nfc import NfcImportResponse
from app.services import nfc_import_service

router = APIRouter(prefix="/api/nfc", tags=["nfc"])


async def require_nfc_api_key(
    x_nfc_api_key: str | None = Header(default=None, alias="X-NFC-API-Key"),
) -> None:
    """Reject unless the request carries the configured NFC import API key.

    Returns 503 when the feature is unconfigured (empty key) so an empty
    secret can never accidentally authenticate an empty header.
    """
    configured = settings.nfc_import_api_key
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NFC import is not configured",
        )
    if not x_nfc_api_key or not hmac.compare_digest(x_nfc_api_key, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing NFC API key",
        )


@router.post("/import", response_model=NfcImportResponse)
async def import_nfc(
    request: Request,
    _auth: None = Depends(require_nfc_api_key),
    session: AsyncSession = Depends(get_db),
) -> NfcImportResponse:
    """Ingest a raw CP950 door-tap file and per-side gap-fill missing punches."""
    raw = await request.body()
    result = await nfc_import_service.import_nfc_file(session, raw)
    return NfcImportResponse(
        filled_in=result.filled_in,
        filled_out=result.filled_out,
        skipped_already_punched=result.skipped_already_punched,
        skipped_terminated=result.skipped_terminated,
        unknown_emp_ids=result.unknown_emp_ids,
        parse_errors=result.parse_errors,
        affected_days=result.affected_days,
    )
