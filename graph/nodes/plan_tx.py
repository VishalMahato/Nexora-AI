from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session
from app.config import get_settings
from app.contracts.agent_result import AgentResult, Explanation, RiskItem
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.schemas import TxCandidate, TxPlan, TxAction
from graph.state import RunState
from graph.utils.needs_input import set_needs_input
from llm.client import LLMClient
from llm.prompts import build_plan_tx_prompt
from tools.tool_runner import run_tool


def _min_wallet_prompt_view(
    wallet_snapshot: Dict[str, Any],
    *,
    top_erc20: int = 8,
    allowlisted_router_addresses: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Do NOT reinvent snapshot. Just slice/filter the existing structure
    to keep prompt payload small.
    """
    allowlisted_router_addresses = allowlisted_router_addresses or []

    erc20 = wallet_snapshot.get("erc20") or []
    allowances = wallet_snapshot.get("allowances") or []

    erc20_view = erc20[:top_erc20] if isinstance(erc20, list) else []

    if allowlisted_router_addresses and isinstance(allowances, list):
        allowset = {a.lower() for a in allowlisted_router_addresses}
        allowances_view = [
            row for row in allowances
            if isinstance(row, dict) and str(row.get("spender", "")).lower() in allowset
        ]
    else:
        allowances_view = allowances if isinstance(allowances, list) else []

    return {
        "chainId": wallet_snapshot.get("chainId"),
        "walletAddress": wallet_snapshot.get("walletAddress"),
        "native": wallet_snapshot.get("native"),
        "erc20": erc20_view,
        "allowances": allowances_view,
    }


def _plan_tx_stub(planner_input: Dict[str, Any]) -> Dict[str, Any]:
    normalized_intent = (planner_input.get("normalized_intent") or "").strip()
    chain_id = planner_input.get("chain_id")

    text = " ".join(normalized_intent.lower().split())
    match = re.match(
        r"^(send|transfer)\s+([0-9]+(?:\.[0-9]+)?)\s+(eth|matic)\s+to\s+(0x[a-fA-F0-9]{40})$",
        text,
    )
    if not match:
        return {
            "plan_version": 1,
            "type": "noop",
            "reason": "no supported native transfer intent match",
            "normalized_intent": normalized_intent,
            "actions": [],
            "candidates": [],
        }

    if not chain_id:
        return {
            "plan_version": 1,
            "type": "noop",
            "reason": "missing chain_id",
            "normalized_intent": normalized_intent,
            "actions": [],
            "candidates": [],
        }

    amount_str = match.group(2)
    asset = match.group(3).upper()
    to_addr = match.group(4)

    try:
        amount_dec = Decimal(amount_str)
    except InvalidOperation:
        amount_dec = Decimal(0)

    if amount_dec <= 0:
        return {
            "plan_version": 1,
            "type": "noop",
            "reason": "amount must be greater than zero",
            "normalized_intent": normalized_intent,
            "actions": [],
            "candidates": [],
        }

    value_wei = str(int(amount_dec * (Decimal(10) ** 18)))
    if value_wei == "0":
        return {
            "plan_version": 1,
            "type": "noop",
            "reason": "amount too small",
            "normalized_intent": normalized_intent,
            "actions": [],
            "candidates": [],
        }
    candidate = TxCandidate(
        chain_id=int(chain_id),
        to=to_addr,
        data="0x",
        value_wei=value_wei,
        meta={"asset": asset},
    )
    action = TxAction(
        action="TRANSFER",
        amount=amount_str,
        to=to_addr,
        chain_id=int(chain_id),
        meta={"asset": asset},
    )

    return {
        "plan_version": 1,
        "type": "plan",
        "normalized_intent": normalized_intent,
        "actions": [action.model_dump(by_alias=True)],
        "candidates": [candidate.model_dump(by_alias=True)],
    }


def _noop_plan(normalized_intent: str, reason: str) -> Dict[str, Any]:
    return {
        "plan_version": 1,
        "type": "noop",
        "reason": reason,
        "normalized_intent": normalized_intent,
        "actions": [],
        "candidates": [],
    }


def _parse_swap_intent(normalized_intent: str) -> tuple[str | None, str | None, str | None]:
    text = " ".join(normalized_intent.lower().split())
    match = re.match(
        r"^swap(?:\s+([0-9]+(?:\.[0-9]+)?))?(?:\s+([a-zA-Z0-9]+))?(?:\s+to\s+([a-zA-Z0-9]+))?$",
        text,
    )
    if not match:
        return None, None, None
    return match.group(1), match.group(2), match.group(3)


def _parse_transfer_intent(
    normalized_intent: str,
) -> tuple[str | None, str | None, str | None]:
    text = " ".join(normalized_intent.lower().split())
    match = re.match(
        r"^(send|transfer)(?:\s+([0-9]+(?:\.[0-9]+)?))?(?:\s+([a-zA-Z0-9]+))?(?:\s+to\s+(0x[a-fA-F0-9]{40}))?$",
        text,
    )
    if not match:
        return None, None, None
    return match.group(2), match.group(3), match.group(4)


def _amount_to_base_units(amount_str: str, decimals: int) -> int | None:
    try:
        amount = Decimal(str(amount_str))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    scale = Decimal(10) ** decimals
    return int((amount * scale).to_integral_value())


def _format_amount_from_base_units(value: int, decimals: int) -> str:
    if decimals <= 0:
        return str(value)
    scaled = Decimal(value) / (Decimal(10) ** decimals)
    return f"{scaled:.4f}".rstrip("0").rstrip(".")


def _balance_for_symbol(
    wallet_snapshot: Dict[str, Any],
    symbol: str,
    allowlisted_tokens: Dict[str, Any],
) -> tuple[int, int] | None:
    lookup = symbol.strip().upper()
    token_meta = None
    for key, meta in (allowlisted_tokens or {}).items():
        if str(key).upper() == lookup:
            token_meta = meta
            break
    if not isinstance(token_meta, dict):
        return None
    decimals = token_meta.get("decimals")
    if not isinstance(decimals, int):
        return None
    if token_meta.get("is_native"):
        balance_wei = (wallet_snapshot.get("native") or {}).get("balanceWei") or "0"
        try:
            return int(str(balance_wei)), decimals
        except Exception:
            return None
    token_addr = token_meta.get("address")
    if not token_addr:
        return None
    for token in wallet_snapshot.get("erc20") or []:
        if str(token.get("token", "")).lower() != str(token_addr).lower():
            continue
        balance = token.get("balance") or "0"
        try:
            return int(str(balance)), decimals
        except Exception:
            return None
    return 0, decimals


def _required_funds(tx_plan: Dict[str, Any]) -> tuple[str, str] | None:
    actions = tx_plan.get("actions") or []
    if not isinstance(actions, list):
        return None
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = (action.get("action") or "").upper()
        if action_type == "SWAP":
            token_in = action.get("token_in") or action.get("tokenIn")
            amount_in = action.get("amount_in") or action.get("amountIn")
            if token_in and amount_in:
                return str(token_in), str(amount_in)
        if action_type == "TRANSFER":
            amount = action.get("amount")
            meta = action.get("meta") or {}
            asset = meta.get("asset") or action.get("asset") or action.get("token")
            if asset and amount:
                return str(asset), str(amount)
    return None


def _detect_missing_inputs(
    *,
    normalized_intent: str,
    chain_id: int | None,
    wallet_address: str | None,
    allowlisted_tokens: Dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    missing: list[str] = []
    data: dict[str, Any] = {}

    if not chain_id:
        missing.append("chain_id")
    if not wallet_address:
        missing.append("wallet_address")

    text = " ".join(normalized_intent.lower().split())
    if text.startswith("swap"):
        amount, token_in, token_out = _parse_swap_intent(normalized_intent)

        if not amount:
            missing.append("amount_in")
        if not token_in:
            missing.append("token_in")
        if not token_out:
            missing.append("token_out")

        allowset = {k.upper() for k in (allowlisted_tokens or {}).keys()}
        if token_in and token_in.upper() not in allowset:
            missing.append("token_in")
        if token_out and token_out.upper() not in allowset:
            missing.append("token_out")
        if allowset:
            data["token_options"] = sorted(allowset)

    if text.startswith("send") or text.startswith("transfer"):
        amount, asset, to_addr = _parse_transfer_intent(normalized_intent)
        if not amount:
            missing.append("amount")
        if not asset:
            missing.append("asset")
        if not to_addr:
            missing.append("recipient")

    missing = list(dict.fromkeys(missing))
    return missing, data


def plan_tx(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    normalized_intent: str = (state.artifacts.get("normalized_intent") or "").strip()
    wallet_snapshot: Dict[str, Any] = state.artifacts.get("wallet_snapshot") or {}
    chain_id = getattr(state, "chain_id", None)

    allowlisted_tokens = settings.allowlisted_tokens_for_chain(chain_id)
    allowlisted_routers = settings.allowlisted_routers_for_chain(chain_id)
    defaults = {
        "slippage_bps": settings.default_slippage_bps,
        "deadline_seconds": settings.default_deadline_seconds,
        "dex_kind": settings.dex_kind,
    }

    router_addresses: List[str] = []
    for _, rv in allowlisted_routers.items():
        if isinstance(rv, str):
            router_addresses.append(rv)
        elif isinstance(rv, dict) and rv.get("address"):
            router_addresses.append(rv["address"])

    wallet_prompt_view = _min_wallet_prompt_view(
        wallet_snapshot,
        top_erc20=8,
        allowlisted_router_addresses=router_addresses,
    )

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="PLAN_TX",
        status="STARTED",
        input={
            "normalized_intent": normalized_intent,
            "chain_id": chain_id,
            "wallet": {
                "native": wallet_prompt_view.get("native"),
                "erc20_count": len(wallet_snapshot.get("erc20") or []),
                "allowances_count": len(wallet_snapshot.get("allowances") or []),
            },
        },
        agent="LangGraph",
    )

    planner_input = {
        "normalized_intent": normalized_intent,
        "chain_id": chain_id,
        "wallet_snapshot": wallet_prompt_view,
        "allowlisted_tokens": allowlisted_tokens,
        "allowlisted_routers": allowlisted_routers,
        "defaults": defaults,
    }

    state.artifacts["planner_input"] = planner_input

    missing, needs_data = _detect_missing_inputs(
        normalized_intent=normalized_intent,
        chain_id=chain_id,
        wallet_address=state.wallet_address,
        allowlisted_tokens=allowlisted_tokens,
    )
    if missing:
        set_needs_input(
            state,
            missing=missing,
            resume_from="PLAN_TX",
            data=needs_data,
        )
        tx_plan = _noop_plan(normalized_intent, "needs_input")
        state.artifacts["tx_plan"] = tx_plan

        log_step(
            db,
            run_id=state.run_id,
            step_name="PLAN_TX",
            status="DONE",
            output={
                "tx_plan": tx_plan,
                "missing": missing,
                "needs_input": state.artifacts.get("needs_input"),
            },
            agent="LangGraph",
        )
        return state

    try:
        planner_warnings: List[str] = []
        llm_error: str | None = None
        llm_used = False
        fallback_used = False

        tx_plan = None
        if settings.LLM_ENABLED:
            llm_client = LLMClient(
                model=settings.LLM_MODEL,
                provider=settings.LLM_PROVIDER,
                api_key=settings.OPENAI_API_KEY,
                temperature=settings.LLM_TEMPERATURE,
                timeout_s=settings.LLM_TIMEOUT_S,
            )
            prompt = build_plan_tx_prompt(planner_input)
            try:
                raw_plan = run_tool(
                    db,
                    run_id=state.run_id,
                    step_id=step.id,
                    tool_name="llm.plan_tx",
                    request={"planner_input": planner_input, "prompt": prompt},
                    fn=lambda: llm_client.plan_tx(planner_input=planner_input),
                )
                llm_used = True
                tx_plan = TxPlan.model_validate(raw_plan).model_dump(by_alias=True)
            except Exception as e:
                llm_error = f"{type(e).__name__}: {e}"
                planner_warnings.append("llm planner failed; fallback to deterministic stub")
                fallback_used = True


        if tx_plan is None:
            raw_plan = _plan_tx_stub(planner_input)
            tx_plan = TxPlan.model_validate(raw_plan).model_dump(by_alias=True)

        max_actions = 3
        max_candidates = 3
        if len(tx_plan.get("actions") or []) > max_actions:
            planner_warnings.append("planner output exceeded action limit; converted to noop")
            tx_plan = _noop_plan(normalized_intent, "planner output exceeded action limit")
            fallback_used = True
        if len(tx_plan.get("candidates") or []) > max_candidates:
            planner_warnings.append("planner output exceeded candidate limit; converted to noop")
            tx_plan = _noop_plan(normalized_intent, "planner output exceeded candidate limit")
            fallback_used = True

        required = _required_funds(tx_plan) if isinstance(tx_plan, dict) else None
        if not required:
            swap_amount, swap_token_in, _ = _parse_swap_intent(normalized_intent)
            if swap_amount and swap_token_in:
                required = (swap_token_in, swap_amount)
        if not required:
            transfer_amount, transfer_asset, _ = _parse_transfer_intent(normalized_intent)
            if transfer_amount and transfer_asset:
                required = (transfer_asset, transfer_amount)
        if required:
            symbol, amount_str = required
            balance_info = _balance_for_symbol(wallet_snapshot, symbol, allowlisted_tokens)
            if balance_info:
                balance_wei, decimals = balance_info
                amount_wei = _amount_to_base_units(amount_str, decimals)
                if amount_wei is not None and balance_wei < amount_wei:
                    balance_fmt = _format_amount_from_base_units(balance_wei, decimals)
                    required_fmt = _format_amount_from_base_units(amount_wei, decimals)
                    questions = [
                        (
                            f"Your {symbol.upper()} balance is {balance_fmt}, which isn't enough "
                            f"to cover {amount_str}. Please add funds or lower the amount."
                        )
                    ]
                    set_needs_input(
                        state,
                        questions=questions,
                        missing=[],
                        resume_from="PLAN_TX",
                        data={
                            "insufficient_balance": True,
                            "asset": symbol.upper(),
                            "balance": balance_fmt,
                            "required": required_fmt,
                        },
                    )
                    planner_warnings.append("insufficient balance for requested amount")
                    tx_plan = _noop_plan(normalized_intent, "insufficient balance")
                    fallback_used = True

        allowlisted_to = settings.allowlisted_to_set()
        if allowlisted_to:
            non_allowlisted = [
                (c.get("to") or "").lower()
                for c in (tx_plan.get("candidates") or [])
                if (c.get("to") or "").lower() not in allowlisted_to
            ]
            if non_allowlisted:
                planner_warnings.append("target not in allowlist; policy may block")

        if planner_warnings:
            state.artifacts["planner_warnings"] = planner_warnings
        if fallback_used:
            state.artifacts["planner_fallback"] = {"used": True, "error": llm_error}
        if llm_error:
            state.artifacts["planner_llm_error"] = llm_error
        state.artifacts["planner_llm_used"] = llm_used
        state.artifacts["tx_plan"] = tx_plan

        risk_items = [
            RiskItem(severity="MED", title="Planner warning", detail=warning)
            for warning in planner_warnings
        ]
        summary = (
            "Planner returned a noop plan."
            if tx_plan.get("type") == "noop"
            else "Planner produced a transaction plan."
        )
        if fallback_used:
            summary = f"{summary} Fallback planner was used."
        status = "WARN" if planner_warnings or fallback_used else "OK"
        errors = [llm_error] if llm_error else None

        planner_result = AgentResult(
            agent="planner",
            step_name="PLAN_TX",
            status=status,
            output={"tx_plan": tx_plan},
            explanation=Explanation(
                summary=summary,
                assumptions=[],
                why_safe=[],
                risks=risk_items,
                next_steps=[],
            ),
            confidence=None,
            sources=[
                "normalized_intent",
                "wallet_snapshot",
                "allowlisted_tokens",
                "allowlisted_routers",
                "defaults",
            ],
            errors=errors,
        ).to_public_dict()

        put_artifact(state, "planner_result", planner_result)
        planner_event = agent_result_to_timeline(planner_result)
        planner_event["attempt"] = state.attempt
        append_timeline_event(state, planner_event)

        log_step(
            db,
            run_id=state.run_id,
            step_name="PLAN_TX",
            status="DONE",
            output={
                "tx_plan": tx_plan,
                "planner_warnings": planner_warnings,
                "llm_error": llm_error,
                "llm_used": llm_used,
                "planner_result": planner_result,
            },
            agent="LangGraph",
        )
        return state

    except Exception as e:
        log_step(
            db,
            run_id=state.run_id,
            step_name="PLAN_TX",
            status="FAILED",
            error=f"{type(e).__name__}: {e}",
            agent="LangGraph",
        )
        raise
