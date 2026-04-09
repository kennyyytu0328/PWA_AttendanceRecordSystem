"""Authenticator repository — async CRUD for WebAuthn credentials."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.authenticator import Authenticator


async def create_authenticator(
    session: AsyncSession, authenticator: Authenticator
) -> Authenticator:
    """Persist a new authenticator and return the refreshed instance."""
    session.add(authenticator)
    await session.commit()
    await session.refresh(authenticator)
    return authenticator


async def find_by_credential_id(
    session: AsyncSession, credential_id: str
) -> Authenticator | None:
    """Return the authenticator matching *credential_id*, or None."""
    result = await session.execute(
        select(Authenticator).where(Authenticator.credential_id == credential_id)
    )
    return result.scalars().first()


async def find_by_employee_id(
    session: AsyncSession, emp_id: str
) -> list[Authenticator]:
    """Return all authenticators registered for *emp_id*."""
    result = await session.execute(
        select(Authenticator).where(Authenticator.emp_id == emp_id)
    )
    return list(result.scalars().all())


async def update_sign_count(
    session: AsyncSession, credential_id: str, new_count: int
) -> Authenticator | None:
    """Update sign_count for *credential_id*; return updated record or None."""
    result = await session.execute(
        select(Authenticator).where(Authenticator.credential_id == credential_id)
    )
    authenticator = result.scalars().first()
    if authenticator is None:
        return None

    authenticator.sign_count = new_count
    session.add(authenticator)
    await session.commit()
    await session.refresh(authenticator)
    return authenticator


async def delete_authenticator(
    session: AsyncSession, credential_id: str
) -> bool:
    """Delete the authenticator with *credential_id*; return True if found."""
    result = await session.execute(
        select(Authenticator).where(Authenticator.credential_id == credential_id)
    )
    authenticator = result.scalars().first()
    if authenticator is None:
        return False

    await session.delete(authenticator)
    await session.commit()
    return True


async def delete_all_by_employee(
    session: AsyncSession, emp_id: str
) -> int:
    """Delete all authenticators for *emp_id*; return count deleted."""
    result = await session.execute(
        select(Authenticator).where(Authenticator.emp_id == emp_id)
    )
    authenticators = list(result.scalars().all())
    for auth in authenticators:
        await session.delete(auth)
    if authenticators:
        await session.commit()
    return len(authenticators)
