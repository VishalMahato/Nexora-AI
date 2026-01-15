from __future__ import annotations

from db.models.run import RunStatus
from db.repos.runs_repo import create_run
from db.session import SessionLocal
from graph.nodes.plan_tx import plan_tx
from graph.state import RunState


def _run_plan_tx(*, intent: str, chain_id, wallet_address):
    db = SessionLocal()
    try:
        run = create_run(
            db,
            intent=intent,
            wallet_address=wallet_address or "0x1111111111111111111111111111111111111111",
            chain_id=chain_id or 1,
        )
        state = RunState(
            run_id=run.id,
            intent=run.intent,
            status=RunStatus.RUNNING,
            chain_id=chain_id,
            wallet_address=wallet_address,
            artifacts={"normalized_intent": intent, "wallet_snapshot": {}},
        )
        config = {"configurable": {"db": db}}
        return plan_tx(state, config)
    finally:
        db.close()


def test_plan_tx_missing_chain_id_sets_needs_input():
    state = _run_plan_tx(
        intent="send 1 eth to 0x1111111111111111111111111111111111111111",
        chain_id=None,
        wallet_address="0x1111111111111111111111111111111111111111",
    )
    needs = state.artifacts.get("needs_input") or {}
    assert "chain_id" in needs.get("missing", [])


def test_plan_tx_missing_wallet_sets_needs_input():
    state = _run_plan_tx(
        intent="send 1 eth to 0x1111111111111111111111111111111111111111",
        chain_id=1,
        wallet_address=None,
    )
    needs = state.artifacts.get("needs_input") or {}
    assert "wallet_address" in needs.get("missing", [])


def test_plan_tx_swap_missing_amount():
    state = _run_plan_tx(
        intent="swap usdc to weth",
        chain_id=1,
        wallet_address="0x1111111111111111111111111111111111111111",
    )
    needs = state.artifacts.get("needs_input") or {}
    assert "amount_in" in needs.get("missing", [])


def test_plan_tx_swap_missing_token_out():
    state = _run_plan_tx(
        intent="swap 1 usdc",
        chain_id=1,
        wallet_address="0x1111111111111111111111111111111111111111",
    )
    needs = state.artifacts.get("needs_input") or {}
    assert "token_out" in needs.get("missing", [])
