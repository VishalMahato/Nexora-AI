from __future__ import annotations

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from chain.client import ChainClient
from db.repos.run_steps_repo import log_step
from graph.state import RunState


def _build_tx_dict(candidate: Dict[str, Any], wallet_address: str | None) -> Dict[str, Any]:
    tx: Dict[str, Any] = {
        "to": candidate.get("to"),
        "data": candidate.get("data") or "0x",
    }

    value = candidate.get("valueWei")
    if value is None:
        value = candidate.get("value_wei")
    if value is None:
        value = candidate.get("value")
    if value is not None:
        try:
            tx["value"] = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"invalid valueWei: {value!r}")

    if wallet_address:
        tx["from"] = wallet_address

    return tx


def simulate_txs(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    tx_plan = state.artifacts.get("tx_plan") or {}

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="SIMULATE_TXS",
        status="STARTED",
        input={
            "tx_plan_type": tx_plan.get("type"),
            "num_candidates": len(tx_plan.get("candidates", [])),
        },
        agent="GRAPH",
    )

    candidates = tx_plan.get("candidates") or []
    if tx_plan.get("type") == "noop" or not candidates:
        simulation_result = {"status": "skipped", "reason": "no transactions to simulate"}
        state.artifacts["simulation"] = simulation_result

        log_step(
            db,
            run_id=state.run_id,
            step_name="SIMULATE_TXS",
            status="DONE",
            output=simulation_result,
            agent="GRAPH",
        )
        return state

    client = ChainClient()
    results = []
    num_success = 0
    num_failed = 0

    for tx in candidates:
        chain_id = tx.get("chain_id") or tx.get("chainId") or state.chain_id or 0
        tx_dict = _build_tx_dict(tx, state.wallet_address)

        result = {
            "tx": tx,
            "success": True,
            "gasEstimate": None,
            "fee": None,
            "error": None,
        }

        try:
            data = (tx_dict.get("data") or "0x").lower()
            if data != "0x":
                client.eth_call(
                    db=db,
                    run_id=state.run_id,
                    step_id=step.id,
                    chain_id=chain_id,
                    tx=tx_dict,
                )

            gas_estimate = client.estimate_gas(
                db=db,
                run_id=state.run_id,
                step_id=step.id,
                chain_id=chain_id,
                tx=tx_dict,
            )

            fee_quote = client.get_fee_quote(
                db=db,
                run_id=state.run_id,
                step_id=step.id,
                chain_id=chain_id,
            )

            result["gasEstimate"] = str(gas_estimate)
            result["fee"] = fee_quote
        except Exception as e:
            result["success"] = False
            result["error"] = f"{type(e).__name__}: {e}"

        if result["success"]:
            num_success += 1
        else:
            num_failed += 1

        results.append(result)

    simulation_result = {
        "status": "completed",
        "results": results,
        "summary": {"num_success": num_success, "num_failed": num_failed},
    }
    state.artifacts["simulation"] = simulation_result

    log_step(
        db,
        run_id=state.run_id,
        step_name="SIMULATE_TXS",
        status="DONE",
        output=simulation_result,
        agent="GRAPH",
    )
    return state
