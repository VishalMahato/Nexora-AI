from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.services.runs_service import create_run_with_audit, start_run_sync


def create_run_from_action(
    *,
    db: Session,
    intent: str,
    wallet_address: str,
    chain_id: int,
) -> UUID:
    return create_run_with_audit(
        db=db,
        intent=intent,
        wallet_address=wallet_address,
        chain_id=chain_id,
        agent="CHAT",
        tool_name="chat_create_run",
    )


def start_run_for_action(*, db: Session, run_id: UUID) -> dict:
    return start_run_sync(db=db, run_id=run_id)
