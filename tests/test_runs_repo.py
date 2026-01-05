from __future__ import annotations

import pytest
from sqlalchemy import text

from db.session import SessionLocal  # using your existing session factory
from db.repos.runs_repo import create_run, get_run, update_run_status
from app.domain.run_status import RunStatus


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        # quick smoke check that DB is reachable
        session.execute(text("SELECT 1"))
        yield session
    finally:
        session.close()


def test_create_and_fetch_run(db):
    run = create_run(
        db,
        intent="Swap 50 USDC to ETH on Uniswap with low slippage",
        wallet_address="0x2c...9A1F",
        chain_id=1,
    )
    fetched = get_run(db, run.id)
    assert fetched is not None
    assert fetched.id == run.id
    assert fetched.status == RunStatus.CREATED.value
    assert fetched.chain_id == 1


def test_valid_status_transition(db):
    run = create_run(db, intent="Check balances", wallet_address="0xabc", chain_id=1)
    updated = update_run_status(db, run_id=run.id, to_status=RunStatus.RUNNING, expected_from=RunStatus.CREATED)
    assert updated.status == RunStatus.RUNNING.value


def test_invalid_status_transition_rejected(db):
    run = create_run(db, intent="Jump states", wallet_address="0xdef", chain_id=1)
    with pytest.raises(ValueError):
        update_run_status(db, run_id=run.id, to_status=RunStatus.APPROVED_READY)
