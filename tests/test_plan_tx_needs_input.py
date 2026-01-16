from __future__ import annotations

from unittest.mock import patch

from db.models.run import RunStatus
from db.repos.runs_repo import create_run
from db.session import SessionLocal
from graph.nodes.plan_tx import plan_tx
from graph.state import RunState
from app.config import get_settings


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


def _run_plan_tx_with_snapshot(*, intent: str, chain_id, wallet_address, wallet_snapshot):
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
            artifacts={"normalized_intent": intent, "wallet_snapshot": wallet_snapshot},
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


def test_plan_tx_insufficient_balance_sets_needs_input(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    get_settings.cache_clear()

    wallet_snapshot = {
        "chainId": 1,
        "walletAddress": "0x1111111111111111111111111111111111111111",
        "native": {"balanceWei": "0"},
        "erc20": [
            {
                "token": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "symbol": "USDC",
                "decimals": 6,
                "balance": "0",
            }
        ],
        "allowances": [],
    }

    llm_plan = {
        "plan_version": 1,
        "type": "plan",
        "normalized_intent": "swap 1 usdc to weth",
        "actions": [
            {
                "action": "SWAP",
                "token_in": "USDC",
                "token_out": "WETH",
                "amount_in": "1",
                "slippage_bps": 50,
                "recipient": "0x1111111111111111111111111111111111111111",
                "router_key": "UNISWAP_V2_ROUTER",
                "deadline_seconds": 1200,
            }
        ],
        "candidates": [],
    }

    with patch("llm.client.LLMClient.plan_tx", return_value=llm_plan):
        state = _run_plan_tx_with_snapshot(
            intent="swap 1 usdc to weth",
            chain_id=1,
            wallet_address="0x1111111111111111111111111111111111111111",
            wallet_snapshot=wallet_snapshot,
        )

    needs = state.artifacts.get("needs_input") or {}
    questions = needs.get("questions") or []
    assert questions
    assert "balance" in questions[0].lower()
    tx_plan = state.artifacts.get("tx_plan") or {}
    assert tx_plan.get("type") == "noop"
    get_settings.cache_clear()
