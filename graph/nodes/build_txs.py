from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from chain.client import ChainClient
from db.repos.run_steps_repo import log_step
from defi.compiler_uniswap_v2 import compile_uniswap_v2_plan
from graph.state import RunState

import time


def build_txs(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()
    client = ChainClient()

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="BUILD_TXS",
        status="STARTED",
        input={
            "normalized_intent": state.artifacts.get("normalized_intent"),
            "has_wallet_snapshot": "wallet_snapshot" in state.artifacts,
        },
        agent="GRAPH",
    )

    normalized_intent = (state.artifacts.get("normalized_intent") or "").lower().strip()

    existing_tx_plan = state.artifacts.get("tx_plan")
    if existing_tx_plan:
        tx_plan = existing_tx_plan
    else:
        tx_plan = {
            "type": "noop",
            "reason": "tx planning not implemented yet (F11 Part 2).",
            "normalized_intent": normalized_intent,
            "candidates": [],
        }
        state.artifacts["tx_plan"] = tx_plan

    actions = tx_plan.get("actions") or []
    if tx_plan.get("type") == "noop" or not actions:
        log_step(
            db,
            run_id=state.run_id,
            step_name="BUILD_TXS",
            status="DONE",
            output=tx_plan,
            agent="GRAPH",
        )
        return state

    allowlisted_tokens = settings.allowlisted_tokens_for_chain(state.chain_id)
    allowlisted_routers = settings.allowlisted_routers_for_chain(state.chain_id)
    if settings.dex_kind != "uniswap_v2":
        raise ValueError(f"unsupported dex_kind: {settings.dex_kind}")

    def get_amounts_out(router_address: str, data: str) -> str:
        return client.eth_call(
            db=db,
            run_id=state.run_id,
            step_id=step.id,
            chain_id=state.chain_id or 0,
            tx={"to": router_address, "data": data},
        )

    block_number = None
    try:
        block_number = client.get_block_number(
            db=db,
            run_id=state.run_id,
            step_id=step.id,
            chain_id=state.chain_id or 0,
        )
    except Exception:
        block_number = None

    tx_requests, candidates, quotes = compile_uniswap_v2_plan(
        chain_id=state.chain_id or 0,
        actions=actions,
        wallet_address=state.wallet_address or "",
        allowlisted_tokens=allowlisted_tokens,
        allowlisted_routers=allowlisted_routers,
        get_amounts_out=get_amounts_out,
        block_number=block_number,
        default_slippage_bps=settings.default_slippage_bps,
        default_deadline_seconds=settings.default_deadline_seconds,
        now_ts=int(time.time()),
    )

    if candidates:
        tx_plan["candidates"] = candidates
    state.artifacts["tx_plan"] = tx_plan
    state.artifacts["tx_requests"] = tx_requests
    if quotes:
        state.artifacts["quote"] = quotes if len(quotes) > 1 else quotes[0]

    log_step(
        db,
        run_id=state.run_id,
        step_name="BUILD_TXS",
        status="DONE",
        output={
            "tx_plan": tx_plan,
            "tx_requests": tx_requests,
            "quote": state.artifacts.get("quote"),
        },
        agent="GRAPH",
    )
    return state
