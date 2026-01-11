from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from chain.client import ChainClient
from db.repos.run_steps_repo import log_step
from graph.state import RunState


def wallet_snapshot(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    client = ChainClient()
    settings = get_settings()

    log_step(
        db,
        run_id=state.run_id,
        step_name="WALLET_SNAPSHOT",
        status="STARTED",
        input={"chainId": state.chain_id, "walletAddress": state.wallet_address},
        agent="GRAPH",
    )

    try:
        allowlisted_tokens = settings.allowlisted_tokens_for_chain(state.chain_id)
        allowlisted_routers = settings.allowlisted_routers_for_chain(state.chain_id)

        token_addresses = []
        for token_meta in allowlisted_tokens.values():
            if isinstance(token_meta, dict) and token_meta.get("address"):
                if token_meta.get("is_native"):
                    continue
                token_addresses.append(token_meta["address"])

        router_addresses = []
        for router_meta in allowlisted_routers.values():
            if isinstance(router_meta, str):
                router_addresses.append(router_meta)
            elif isinstance(router_meta, dict) and router_meta.get("address"):
                router_addresses.append(router_meta["address"])

        allowances = []
        for token_addr in token_addresses:
            for router_addr in router_addresses:
                allowances.append({"token": token_addr, "spender": router_addr})

        snapshot = client.wallet_snapshot(
            db=db,
            run_id=state.run_id,
            step_id=None,
            chain_id=state.chain_id or 0,
            wallet_address=state.wallet_address or "",
            erc20_tokens=token_addresses,
            allowances=allowances,
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
