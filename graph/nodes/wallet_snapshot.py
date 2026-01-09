from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from chain.client import ChainClient
from db.repos.run_steps_repo import log_step
from graph.state import RunState


def wallet_snapshot(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    client = ChainClient()

    log_step(
        db,
        run_id=state.run_id,
        step_name="WALLET_SNAPSHOT",
        status="STARTED",
        input={"chainId": state.chain_id, "walletAddress": state.wallet_address},
        agent="GRAPH",
    )

    try:
        snapshot = client.wallet_snapshot(
            db=db,
            run_id=state.run_id,
            step_id=None,
            chain_id=state.chain_id or 0,
            wallet_address=state.wallet_address or "",
            erc20_tokens=[],
            allowances=[],
        )

        state.artifacts["wallet_snapshot"] = snapshot

        log_step(
            db,
            run_id=state.run_id,
            step_name="WALLET_SNAPSHOT",
            status="DONE",
            output=snapshot,
            agent="GRAPH",
        )
        return state

    except Exception as e:
        log_step(
            db,
            run_id=state.run_id,
            step_name="WALLET_SNAPSHOT",
            status="FAILED",
            output={"error": f"{type(e).__name__}: {e}"},
            agent="GRAPH",
        )
        raise
