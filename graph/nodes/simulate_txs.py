from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
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


def _tx_request_id(tx_request: Dict[str, Any], index: int) -> str:
    return tx_request.get("txRequestId") or f"tx-{index + 1}"


def _order_tx_requests(tx_requests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    priorities = {"APPROVE": 0, "SWAP": 1}
    indexed = list(enumerate(tx_requests))
    indexed.sort(
        key=lambda pair: (
            priorities.get((pair[1].get("meta") or {}).get("kind", "").upper(), 2),
            pair[0],
        )
    )
    return [item for _, item in indexed]


def _token_address(
    allowlisted_tokens: Dict[str, Dict[str, Any]],
    symbol: str | None,
) -> str | None:
    if not symbol:
        return None
    lookup = symbol.strip().upper()
    for key, meta in (allowlisted_tokens or {}).items():
        if key.upper() != lookup:
            continue
        address = meta.get("address") if isinstance(meta, dict) else None
        if address:
            return str(address).lower()
    return None


def _router_address(
    allowlisted_routers: Dict[str, Any],
    router_key: str | None,
) -> str | None:
    if not router_key:
        return None
    meta = allowlisted_routers.get(router_key) or allowlisted_routers.get(router_key.upper())
    if isinstance(meta, str):
        return meta.lower()
    if isinstance(meta, dict) and meta.get("address"):
        return str(meta["address"]).lower()
    return None


def _wallet_has_balance(
    wallet_snapshot: Dict[str, Any],
    token_address: str | None,
    amount_base_units: str | None,
) -> bool:
    if not token_address or amount_base_units is None:
        return False
    try:
        needed = int(str(amount_base_units))
    except Exception:
        return False
    for token in wallet_snapshot.get("erc20") or []:
        if str(token.get("token", "")).lower() != token_address:
            continue
        try:
            balance = int(str(token.get("balance") or "0"))
        except Exception:
            return False
        return balance >= needed
    return False


def _find_matching_approve(
    tx_requests: List[Dict[str, Any]],
    swap_tx: Dict[str, Any],
    allowlisted_tokens: Dict[str, Dict[str, Any]],
    allowlisted_routers: Dict[str, Any],
) -> Dict[str, Any] | None:
    meta = swap_tx.get("meta") or {}
    if (meta.get("kind") or "").upper() != "SWAP":
        return None
    token_in = _token_address(allowlisted_tokens, meta.get("tokenIn"))
    if not token_in:
        return None
    swap_router = (swap_tx.get("to") or "").lower() or _router_address(
        allowlisted_routers,
        meta.get("routerKey"),
    )
    try:
        amount_in = int(str(meta.get("amountInBaseUnits") or "0"))
    except Exception:
        return None
    for tx in tx_requests:
        approve_meta = tx.get("meta") or {}
        if (approve_meta.get("kind") or "").upper() != "APPROVE":
            continue
        approve_token = _token_address(allowlisted_tokens, approve_meta.get("token"))
        if not approve_token or approve_token != token_in:
            continue
        spender_addr = _router_address(
            allowlisted_routers,
            approve_meta.get("spender") or approve_meta.get("routerKey"),
        )
        if not spender_addr or (swap_router and spender_addr != swap_router):
            continue
        try:
            approve_amount = int(str(approve_meta.get("amountBaseUnits") or "0"))
        except Exception:
            continue
        if approve_amount < amount_in:
            continue
        return tx
    return None


def _is_allowance_failure(error: str | None) -> bool:
    if not error:
        return False
    hay = error.lower()
    patterns = [
        "transfer_from_failed",
        "transferhelper: transfer_from_failed",
        "insufficient allowance",
        "transfer amount exceeds allowance",
        "erc20: insufficient allowance",
    ]
    return any(pat in hay for pat in patterns)


def _simulate_single(
    *,
    client: ChainClient,
    db: Session,
    run_id: str,
    step_id: int,
    chain_id: int,
    wallet_address: str | None,
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    results = []
    num_success = 0
    num_failed = 0

    for tx in candidates:
        effective_chain_id = tx.get("chain_id") or tx.get("chainId") or chain_id
        tx_dict = _build_tx_dict(tx, wallet_address)
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
                    run_id=run_id,
                    step_id=step_id,
                    chain_id=effective_chain_id,
                    tx=tx_dict,
                )

            gas_estimate = client.estimate_gas(
                db=db,
                run_id=run_id,
                step_id=step_id,
                chain_id=effective_chain_id,
                tx=tx_dict,
            )

            fee_quote = client.get_fee_quote(
                db=db,
                run_id=run_id,
                step_id=step_id,
                chain_id=effective_chain_id,
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

    return {
        "status": "completed",
        "mode": "single",
        "results": results,
        "summary": {"num_success": num_success, "num_failed": num_failed},
    }


def _simulate_sequential(
    *,
    client: ChainClient,
    db: Session,
    run_id: str,
    step_id: int,
    chain_id: int,
    wallet_address: str | None,
    wallet_snapshot: Dict[str, Any],
    tx_requests: List[Dict[str, Any]],
    allowlisted_tokens: Dict[str, Dict[str, Any]],
    allowlisted_routers: Dict[str, Any],
) -> Dict[str, Any]:
    ordered = _order_tx_requests(tx_requests)
    results = []
    num_success = 0
    num_failed = 0
    sequence: List[str] = []

    for idx, tx_request in enumerate(ordered):
        tx_id = _tx_request_id(tx_request, idx)
        sequence.append(tx_id)
        effective_chain_id = (
            tx_request.get("chain_id") or tx_request.get("chainId") or chain_id
        )
        tx_dict = _build_tx_dict(tx_request, wallet_address)

        result = {
            "tx": tx_request,
            "txRequestId": tx_id,
            "success": True,
            "assumed_success": False,
            "assumption_reason": None,
            "gasEstimate": None,
            "fee": None,
            "error": None,
        }

        try:
            data = (tx_dict.get("data") or "0x").lower()
            if data != "0x":
                client.eth_call(
                    db=db,
                    run_id=run_id,
                    step_id=step_id,
                    chain_id=effective_chain_id,
                    tx=tx_dict,
                )

            gas_estimate = client.estimate_gas(
                db=db,
                run_id=run_id,
                step_id=step_id,
                chain_id=effective_chain_id,
                tx=tx_dict,
            )

            fee_quote = client.get_fee_quote(
                db=db,
                run_id=run_id,
                step_id=step_id,
                chain_id=effective_chain_id,
            )

            result["gasEstimate"] = str(gas_estimate)
            result["fee"] = fee_quote
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            kind = ((tx_request.get("meta") or {}).get("kind") or "").upper()
            if kind == "SWAP" and _is_allowance_failure(error):
                approve_tx = _find_matching_approve(
                    tx_requests,
                    tx_request,
                    allowlisted_tokens,
                    allowlisted_routers,
                )
                token_in = _token_address(allowlisted_tokens, (tx_request.get("meta") or {}).get("tokenIn"))
                amount_in = (tx_request.get("meta") or {}).get("amountInBaseUnits")
                has_balance = _wallet_has_balance(wallet_snapshot, token_in, amount_in)
                if approve_tx and has_balance:
                    result["assumed_success"] = True
                    result["assumption_reason"] = "ALLOWANCE_NOT_APPLIED_IN_SIMULATION"
                    result["error"] = error
                else:
                    result["success"] = False
                    result["error"] = error
            else:
                result["success"] = False
                result["error"] = error

        if result["success"] or result["assumed_success"]:
            num_success += 1
        else:
            num_failed += 1

        results.append(result)

    return {
        "status": "completed",
        "mode": "sequential",
        "sequence": sequence,
        "override_support": "unsupported",
        "overrides_used": False,
        "results": results,
        "summary": {"num_success": num_success, "num_failed": num_failed},
    }


def simulate_txs(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()
    tx_plan = state.artifacts.get("tx_plan") or {}
    tx_requests = state.artifacts.get("tx_requests") or []

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="SIMULATE_TXS",
        status="STARTED",
        input={
            "tx_plan_type": tx_plan.get("type"),
            "num_candidates": len(tx_plan.get("candidates", [])),
            "num_tx_requests": len(tx_requests) if isinstance(tx_requests, list) else 0,
        },
        agent="GRAPH",
    )

    candidates = tx_plan.get("candidates") or []
    if tx_plan.get("type") == "noop" or (not candidates and not tx_requests):
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
    chain_id = state.chain_id or 0
    tx_requests_list = [r for r in tx_requests if isinstance(r, dict)] if isinstance(tx_requests, list) else []
    if tx_requests_list and len(tx_requests_list) > 1:
        allowlisted_tokens = settings.allowlisted_tokens_for_chain(chain_id)
        allowlisted_routers = settings.allowlisted_routers_for_chain(chain_id)
        simulation_result = _simulate_sequential(
            client=client,
            db=db,
            run_id=state.run_id,
            step_id=step.id,
            chain_id=chain_id,
            wallet_address=state.wallet_address,
            wallet_snapshot=state.artifacts.get("wallet_snapshot") or {},
            tx_requests=tx_requests_list,
            allowlisted_tokens=allowlisted_tokens,
            allowlisted_routers=allowlisted_routers,
        )
    else:
        simulation_result = _simulate_single(
            client=client,
            db=db,
            run_id=state.run_id,
            step_id=step.id,
            chain_id=chain_id,
            wallet_address=state.wallet_address,
            candidates=candidates,
        )

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
