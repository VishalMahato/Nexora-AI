# Graph Nodes

## Roles and Purpose
- `INPUT_NORMALIZE`: Normalize raw intent, record attempt metadata, and log the step.
- `PRECHECK`: Validate intent, chain, and wallet format before RPC work.
- `WALLET_SNAPSHOT`: Fetch wallet balances/allowances from RPC using allowlists; store wallet_snapshot.
- `PLAN_TX`: Plan transactions using LLM or deterministic stub; produce tx_plan and planner_result.
- `BUILD_TXS`: Compile tx_plan actions into tx_requests/candidates (Uniswap V2) and optional quote.
- `SIMULATE_TXS`: Simulate candidates/tx_requests (single or sequential) and store simulation results.
- `POLICY_EVAL`: Run policy checks and derive decision; store policy_result and decision.
- `SECURITY_EVAL`: Wrap policy outcomes into security AgentResult and timeline entry.
- `JUDGE_AGENT`: LLM judge review (or fallback), store judge_result and timeline entry.
- `REPAIR_ROUTER`: Decide whether to retry planning (REPAIR_PLAN_TX) or finalize.
- `REPAIR_PLAN_TX`: Replan using LLM or stub based on judge issues; track history and timeline.
- `CLARIFY`: Ensure `needs_input.questions` exists before FINALIZE.
- `FINALIZE`: Compose `assistant_message` (LLM + fallback) and log FINALIZE step.

## Node Source Files

### INPUT_NORMALIZE

Path: `graph/nodes/input_normalize.py`

```python
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from db.repos.run_steps_repo import log_step
from graph.state import RunState


def input_normalize(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    log_step(
        db,
        run_id=state.run_id,
        step_name="INPUT_NORMALIZE",
        status="STARTED",
        input={"intent": state.intent},
        agent="LangGraph",
    )

    normalized_intent = state.intent.strip()
    state.artifacts["normalized_intent"] = normalized_intent
    state.artifacts["attempt"] = state.attempt
    state.artifacts["max_attempts"] = state.max_attempts

    log_step(
        db,
        run_id=state.run_id,
        step_name="INPUT_NORMALIZE",
        status="DONE",
        output={
            "normalized_intent": normalized_intent,
            "attempt": state.attempt,
            "max_attempts": state.max_attempts,
        },
        agent="LangGraph",
    )
    return state
```

## Change log

- 2026-01-13: Initial version.

### PRECHECK

Path: `graph/nodes/precheck.py`

```python
from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session
from web3 import Web3

from app.config import get_settings
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event
from graph.state import RunState
from graph.utils.needs_input import set_needs_input


def _allowed_chain_ids(settings) -> list[int]:
    allowlist = set()
    for source in (settings.allowlisted_tokens, settings.allowlisted_routers):
        if isinstance(source, dict):
            allowlist.update(source.keys())
    chain_ids: list[int] = []
    for raw in allowlist:
        try:
            chain_ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    return sorted(set(chain_ids))


def _is_valid_wallet(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    if not value.startswith("0x") or len(value) != 42:
        return False
    return Web3.is_address(value)


def precheck(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    log_step(
        db,
        run_id=state.run_id,
        step_name="PRECHECK",
        status="STARTED",
        input={
            "chain_id": state.chain_id,
            "wallet_address": state.wallet_address,
            "normalized_intent": state.artifacts.get("normalized_intent"),
        },
        agent="LangGraph",
    )

    if state.artifacts.get("fatal_error") or state.artifacts.get("needs_input"):
        log_step(
            db,
            run_id=state.run_id,
            step_name="PRECHECK",
            status="DONE",
            output={"skipped": True},
            agent="LangGraph",
        )
        return state

    missing: list[str] = []
    data: dict[str, Any] = {}

    normalized_intent = state.artifacts.get("normalized_intent")
    if not isinstance(normalized_intent, str):
        state.artifacts["fatal_error"] = {
            "step": "PRECHECK",
            "type": "INVALID_INTENT",
            "message": "Intent is not a valid string.",
        }
    else:
        if not normalized_intent.strip():
            missing.append("intent")

    chain_id = state.chain_id
    if not chain_id:
        missing.append("chain_id")
    else:
        allowed = _allowed_chain_ids(settings)
        if allowed and chain_id not in allowed:
            missing.append("chain_id")
            data["chain_options"] = allowed

    wallet_address = state.wallet_address
    if not wallet_address:
        missing.append("wallet_address")
    elif not _is_valid_wallet(wallet_address):
        missing.append("wallet_address")

    if missing and "fatal_error" not in state.artifacts:
        set_needs_input(
            state,
            missing=missing,
            resume_from="PRECHECK",
            data=data,
        )
        append_timeline_event(
            state,
            {
                "step": "PRECHECK",
                "status": "DONE",
                "title": "precheck",
                "summary": "Input validation requires clarification.",
                "attempt": state.attempt,
            },
        )

    log_step(
        db,
        run_id=state.run_id,
        step_name="PRECHECK",
        status="DONE",
        output={
            "missing": missing,
            "fatal_error": state.artifacts.get("fatal_error"),
            "needs_input": state.artifacts.get("needs_input"),
        },
        agent="LangGraph",
    )
    return state
```

### WALLET_SNAPSHOT

Path: `graph/nodes/wallet_snapshot.py`

```python
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
```

### PLAN_TX

Path: `graph/nodes/plan_tx.py`

```python
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
```

### BUILD_TXS

Path: `graph/nodes/build_txs.py`

```python
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
```

### SIMULATE_TXS

Path: `graph/nodes/simulate_txs.py`

```python
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
```

### POLICY_EVAL

Path: `graph/nodes/policy_eval.py`

```python
from __future__ import annotations

import policy.engine as policy_engine
from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from db.repos.run_steps_repo import log_step
from graph.state import RunState


def policy_eval(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="POLICY_EVAL",
        status="STARTED",
        input={"artifacts_keys": sorted(list(state.artifacts.keys()))},
        agent="LangGraph",
    )

    settings = get_settings()
    policy_result, decision = policy_engine.evaluate_policies(
        state.artifacts,
        allowlisted_to=settings.allowlisted_to_set(),
        allowlisted_tokens=settings.allowlisted_tokens_for_chain(state.chain_id),
        allowlisted_routers=settings.allowlisted_routers_for_chain(state.chain_id),
        min_slippage_bps=settings.min_slippage_bps,
        max_slippage_bps=settings.max_slippage_bps,
    )

    state.artifacts["policy_result"] = policy_result.model_dump()
    state.artifacts["decision"] = decision.model_dump()

    log_step(
        db,
        run_id=state.run_id,
        step_name="POLICY_EVAL",
        status="DONE",
        output={
            "policy_result": state.artifacts["policy_result"],
            "decision": state.artifacts["decision"],
        },
        agent="LangGraph",
    )

    return state
```

### SECURITY_EVAL

Path: `graph/nodes/security_eval.py`

```python
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.contracts.agent_result import AgentResult, Explanation, RiskItem
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.state import RunState
from policy.types import CheckStatus, DecisionAction, PolicyResult, Decision


def security_eval(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    log_step(
        db,
        run_id=state.run_id,
        step_name="SECURITY_EVAL",
        status="STARTED",
        input={"artifacts_keys": sorted(list(state.artifacts.keys()))},
        agent="LangGraph",
    )

    policy_result = PolicyResult.model_validate(state.artifacts.get("policy_result") or {})
    decision = Decision.model_validate(state.artifacts.get("decision") or {})

    warn_count = policy_result.warn_count
    fail_count = policy_result.fail_count
    if decision.action == DecisionAction.BLOCK or fail_count > 0:
        status = "BLOCK"
        summary = "Security evaluation blocked the run."
    elif warn_count > 0:
        status = "WARN"
        summary = "Security evaluation completed with warnings."
    else:
        status = "OK"
        summary = "Security evaluation passed."

    risk_items = []
    for check in policy_result.checks:
        if check.status in {CheckStatus.FAIL, CheckStatus.WARN}:
            severity = "HIGH" if check.status == CheckStatus.FAIL else "MED"
            risk_items.append(
                RiskItem(
                    severity=severity,
                    title=check.title,
                    detail=check.reason or "Policy check flagged an issue.",
                )
            )

    security_result = AgentResult(
        agent="security",
        step_name="SECURITY_EVAL",
        status=status,
        output={
            "policy_result": policy_result.model_dump(),
            "decision": decision.model_dump(),
        },
        explanation=Explanation(
            summary=summary,
            assumptions=[],
            why_safe=[],
            risks=risk_items,
            next_steps=[],
        ),
        confidence=None,
        sources=["tx_plan", "simulation", "wallet_snapshot", "allowlist_to"],
        errors=None,
    ).to_public_dict()

    put_artifact(state, "security_result", security_result)
    security_event = agent_result_to_timeline(security_result)
    security_event["attempt"] = state.attempt
    append_timeline_event(state, security_event)

    log_step(
        db,
        run_id=state.run_id,
        step_name="SECURITY_EVAL",
        status="DONE",
        output={"security_result": security_result},
        agent="LangGraph",
    )

    return state
```

### JUDGE_AGENT

Path: `graph/nodes/judge_agent.py`

```python
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from app.contracts.agent_result import AgentResult, Explanation, RiskItem
from app.contracts.judge_result import JudgeIssueSeverity, JudgeOutput, JudgeVerdict
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.state import RunState
from llm.client import LLMClient
from llm.prompts import build_judge_prompt
from tools.tool_runner import run_tool


def _slice_list(items: Any, *, limit: int) -> List[Any]:
    if not isinstance(items, list):
        return []
    return items[:limit]


def _compact_wallet_snapshot(wallet_snapshot: Dict[str, Any], *, top_erc20: int = 5) -> Dict[str, Any]:
    erc20 = _slice_list(wallet_snapshot.get("erc20"), limit=top_erc20)
    allowances = _slice_list(wallet_snapshot.get("allowances"), limit=top_erc20)
    return {
        "chainId": wallet_snapshot.get("chainId"),
        "walletAddress": wallet_snapshot.get("walletAddress"),
        "native": wallet_snapshot.get("native"),
        "erc20": erc20,
        "allowances": allowances,
    }


def _compact_tx_plan(tx_plan: Dict[str, Any], *, max_items: int = 3) -> Dict[str, Any]:
    actions = _slice_list(tx_plan.get("actions"), limit=max_items)
    candidates = _slice_list(tx_plan.get("candidates"), limit=max_items)
    return {
        "plan_version": tx_plan.get("plan_version"),
        "type": tx_plan.get("type"),
        "reason": tx_plan.get("reason"),
        "normalized_intent": tx_plan.get("normalized_intent"),
        "action_count": len(tx_plan.get("actions") or []),
        "candidate_count": len(tx_plan.get("candidates") or []),
        "actions": actions,
        "candidates": candidates,
    }


def _summarize_simulation(simulation: Dict[str, Any], *, max_failures: int = 3) -> Dict[str, Any]:
    status = simulation.get("status")
    if status == "skipped":
        return {"status": "skipped", "reason": simulation.get("reason")}
    if status != "completed":
        return {"status": status}

    results = simulation.get("results") or []
    failures = []
    for idx, result in enumerate(results):
        if result.get("success") is False:
            failures.append(
                {
                    "index": idx,
                    "error": result.get("error"),
                    "gasEstimate": result.get("gasEstimate"),
                    "fee": result.get("fee"),
                }
            )
        if len(failures) >= max_failures:
            break

    return {
        "status": "completed",
        "summary": simulation.get("summary"),
        "failures": failures,
    }


def _summarize_policy(policy_result: Dict[str, Any], *, max_items: int = 5) -> Dict[str, Any]:
    checks = policy_result.get("checks") or []
    flagged = []
    for check in checks:
        status = check.get("status")
        if status in {"WARN", "FAIL"}:
            flagged.append(
                {
                    "id": check.get("id"),
                    "title": check.get("title"),
                    "status": status,
                    "reason": check.get("reason"),
                }
            )
        if len(flagged) >= max_items:
            break
    return {
        "flagged_checks": flagged,
        "total_checks": len(checks),
    }


def _build_judge_input(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    tx_plan = artifacts.get("tx_plan") or {}
    simulation = artifacts.get("simulation") or {}
    policy_result = artifacts.get("policy_result") or {}
    decision = artifacts.get("decision") or {}
    wallet_snapshot = artifacts.get("wallet_snapshot") or {}
    planner_result = artifacts.get("planner_result") or {}

    return {
        "normalized_intent": artifacts.get("normalized_intent"),
        "tx_plan": _compact_tx_plan(tx_plan),
        "simulation": _summarize_simulation(simulation),
        "policy_result": _summarize_policy(policy_result),
        "decision": {
            "action": decision.get("action"),
            "severity": decision.get("severity"),
            "risk_score": decision.get("risk_score"),
            "summary": decision.get("summary"),
            "reasons": decision.get("reasons"),
        },
        "wallet_snapshot": _compact_wallet_snapshot(wallet_snapshot),
        "planner_summary": {
            "summary": (planner_result.get("explanation") or {}).get("summary"),
            "plan_type": ((planner_result.get("output") or {}).get("tx_plan") or {}).get("type"),
        },
        "prompt_version": "v1",
    }


def _issue_to_risk_item(issue: Dict[str, Any]) -> RiskItem:
    severity = issue.get("severity") or JudgeIssueSeverity.MED.value
    if severity not in {s.value for s in JudgeIssueSeverity}:
        severity = JudgeIssueSeverity.MED.value
    return RiskItem(
        severity=severity,
        title=issue.get("code") or "JUDGE_ISSUE",
        detail=issue.get("message") or "Judge flagged an issue.",
    )


def _fallback_judge_output(message: str) -> JudgeOutput:
    return JudgeOutput(
        verdict=JudgeVerdict.NEEDS_REWORK,
        reasoning_summary=message,
        issues=[],
    )


def judge_agent(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="JUDGE_AGENT",
        status="STARTED",
        input={"artifacts_keys": sorted(list(state.artifacts.keys()))},
        agent="LangGraph",
    )

    judge_input = _build_judge_input(state.artifacts)

    llm_used = False
    llm_error = None
    judge_output: JudgeOutput

    if settings.LLM_ENABLED:
        llm_client = LLMClient(
            model=settings.LLM_MODEL,
            provider=settings.LLM_PROVIDER,
            api_key=settings.OPENAI_API_KEY,
            temperature=settings.LLM_TEMPERATURE,
            timeout_s=settings.LLM_TIMEOUT_S,
        )
        prompt = build_judge_prompt(judge_input)
        try:
            raw_output = run_tool(
                db,
                run_id=state.run_id,
                step_id=step.id,
                tool_name="llm.judge",
                request={"judge_input": judge_input, "prompt": prompt},
                fn=lambda: llm_client.judge(judge_input=judge_input),
            )
            llm_used = True
            judge_output = JudgeOutput.model_validate(raw_output)
        except Exception as e:
            llm_error = f"{type(e).__name__}: {e}"
            judge_output = _fallback_judge_output("Judge failed; manual review required.")
    else:
        judge_output = _fallback_judge_output("Judge disabled; manual review required.")

    verdict = judge_output.verdict.value
    if verdict == JudgeVerdict.BLOCK.value:
        status = "BLOCK"
    elif verdict == JudgeVerdict.NEEDS_REWORK.value:
        status = "WARN"
    else:
        status = "OK"

    issues = [issue.model_dump() for issue in judge_output.issues]
    risk_items = [_issue_to_risk_item(issue) for issue in issues]
    summary = judge_output.reasoning_summary or "Judge completed review."

    judge_result = AgentResult(
        agent="judge",
        step_name="JUDGE_AGENT",
        status=status,
        output={
            "verdict": verdict,
            "reasoning_summary": judge_output.reasoning_summary,
            "issues": issues,
        },
        explanation=Explanation(
            summary=summary,
            assumptions=[],
            why_safe=[],
            risks=risk_items,
            next_steps=[],
        ),
        confidence=None,
        sources=[
            "planner_result",
            "tx_plan",
            "simulation",
            "policy_result",
            "decision",
            "wallet_snapshot",
        ],
        errors=[llm_error] if llm_error else None,
    ).to_public_dict()

    put_artifact(state, "judge_result", judge_result)
    judge_event = agent_result_to_timeline(judge_result)
    judge_event["attempt"] = state.attempt
    append_timeline_event(state, judge_event)

    log_step(
        db,
        run_id=state.run_id,
        step_name="JUDGE_AGENT",
        status="DONE",
        output={
            "judge_result": judge_result,
            "llm_used": llm_used,
            "llm_error": llm_error,
        },
        agent="LangGraph",
    )

    return state
```

### REPAIR_ROUTER

Path: `graph/nodes/repair_router.py`

```python
from __future__ import annotations

from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event
from graph.state import RunState


def _judge_payload(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    judge_result = artifacts.get("judge_result") or {}
    return judge_result.get("output") or {}


def repair_router(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    state.artifacts["attempt"] = state.attempt
    state.artifacts["max_attempts"] = state.max_attempts

    judge_output = _judge_payload(state.artifacts)
    verdict = judge_output.get("verdict")
    issues = judge_output.get("issues") or []

    can_retry = (
        verdict == "NEEDS_REWORK"
        and state.attempt < state.max_attempts
        and isinstance(issues, list)
        and len(issues) > 0
        and settings.LLM_ENABLED
    )

    next_step = "FINALIZE"
    summary = "Routing to finalize."

    if verdict == "BLOCK":
        summary = "Judge blocked; routing to finalize."
    elif verdict == "PASS":
        summary = "Judge passed; routing to finalize."
    elif verdict == "NEEDS_REWORK" and can_retry:
        state.attempt += 1
        state.artifacts["attempt"] = state.attempt
        next_step = "REPAIR_PLAN_TX"
        summary = f"Judge requested rework; retrying (attempt {state.attempt}/{state.max_attempts})."
        state.artifacts["repair_context"] = {
            "attempted": True,
            "attempt": state.attempt,
            "max_attempts": state.max_attempts,
            "judge_issues_used": [issue.get("code") for issue in issues if isinstance(issue, dict)],
        }
    elif verdict == "NEEDS_REWORK" and not settings.LLM_ENABLED:
        summary = "Judge requested rework; repair disabled."
    elif verdict == "NEEDS_REWORK" and state.attempt >= state.max_attempts:
        summary = "Judge requested rework; no retries left."
    elif verdict == "NEEDS_REWORK":
        summary = "Judge requested rework; no usable issues for repair."

    if state.attempt > 1 and verdict in {"PASS", "NEEDS_REWORK"}:
        state.artifacts["repair_summary"] = {
            "attempted": True,
            "success": verdict == "PASS",
            "attempts": state.attempt,
            "max_attempts": state.max_attempts,
        }

    state.artifacts["repair_next_step"] = next_step

    log_step(
        db,
        run_id=state.run_id,
        step_name="REPAIR_ROUTER",
        status="DONE",
        output={
            "verdict": verdict,
            "next_step": next_step,
            "attempt": state.attempt,
            "max_attempts": state.max_attempts,
        },
        agent="LangGraph",
    )

    append_timeline_event(
        state,
        {
            "step": "REPAIR_ROUTER",
            "status": "DONE",
            "title": "repair_router",
            "summary": summary,
            "attempt": state.attempt,
        },
    )

    return state
```

### REPAIR_PLAN_TX

Path: `graph/nodes/repair_plan_tx.py`

```python
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from app.contracts.agent_result import AgentResult, Explanation, RiskItem
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.schemas import TxPlan
from graph.state import RunState
from graph.nodes.plan_tx import _plan_tx_stub
from llm.client import LLMClient
from llm.prompts import build_repair_plan_tx_prompt
from tools.tool_runner import run_tool


def _summarize_plan(tx_plan: Dict[str, Any], *, max_items: int = 3) -> Dict[str, Any]:
    actions = tx_plan.get("actions") or []
    candidates = tx_plan.get("candidates") or []
    return {
        "plan_version": tx_plan.get("plan_version"),
        "type": tx_plan.get("type"),
        "reason": tx_plan.get("reason"),
        "normalized_intent": tx_plan.get("normalized_intent"),
        "action_count": len(actions),
        "candidate_count": len(candidates),
        "actions": actions[:max_items] if isinstance(actions, list) else [],
        "candidates": candidates[:max_items] if isinstance(candidates, list) else [],
    }


def _summarize_simulation(simulation: Dict[str, Any]) -> Dict[str, Any]:
    summary = simulation.get("summary") or {}
    return {
        "status": simulation.get("status"),
        "num_success": summary.get("num_success"),
        "num_failed": summary.get("num_failed"),
    }


def _build_repair_input(state: RunState) -> Dict[str, Any]:
    artifacts = state.artifacts or {}
    judge_output = (artifacts.get("judge_result") or {}).get("output") or {}
    tx_plan = artifacts.get("tx_plan") or {}
    simulation = artifacts.get("simulation") or {}
    wallet_snapshot = artifacts.get("wallet_snapshot") or {}

    return {
        "normalized_intent": artifacts.get("normalized_intent"),
        "chain_id": state.chain_id,
        "previous_plan": _summarize_plan(tx_plan),
        "judge_issues": judge_output.get("issues") or [],
        "simulation_summary": _summarize_simulation(simulation),
        "wallet_hint": {
            "native_balance_wei": (wallet_snapshot.get("native") or {}).get("balanceWei"),
        },
    }


def repair_plan_tx(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="REPAIR_PLAN_TX",
        status="STARTED",
        input={
            "attempt": state.attempt,
            "normalized_intent": state.artifacts.get("normalized_intent"),
        },
        agent="LangGraph",
    )

    repair_input = _build_repair_input(state)
    repair_input.update(
        {
            "allowlisted_tokens": settings.allowlisted_tokens_for_chain(state.chain_id),
            "allowlisted_routers": settings.allowlisted_routers_for_chain(state.chain_id),
            "defaults": {
                "slippage_bps": settings.default_slippage_bps,
                "deadline_seconds": settings.default_deadline_seconds,
                "dex_kind": settings.dex_kind,
            },
        }
    )

    state.artifacts["repair_planner_input"] = repair_input

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
        prompt = build_repair_plan_tx_prompt(repair_input)
        try:
            raw_plan = run_tool(
                db,
                run_id=state.run_id,
                step_id=step.id,
                tool_name="llm.repair_plan_tx",
                request={"repair_input": repair_input, "prompt": prompt},
                fn=lambda: llm_client.repair_plan_tx(repair_input=repair_input),
            )
            llm_used = True
            tx_plan = TxPlan.model_validate(raw_plan).model_dump(by_alias=True)
        except Exception as e:
            llm_error = f"{type(e).__name__}: {e}"
            planner_warnings.append("repair planner failed; fallback to deterministic stub")
            fallback_used = True

    if tx_plan is None:
        raw_plan = _plan_tx_stub(
            {
                "normalized_intent": state.artifacts.get("normalized_intent"),
                "chain_id": state.chain_id,
            }
        )
        tx_plan = TxPlan.model_validate(raw_plan).model_dump(by_alias=True)

    max_actions = 3
    max_candidates = 3
    if len(tx_plan.get("actions") or []) > max_actions:
        planner_warnings.append("repair plan exceeded action limit; converted to noop")
        tx_plan = {
            "plan_version": 1,
            "type": "noop",
            "reason": "repair output exceeded action limit",
            "normalized_intent": state.artifacts.get("normalized_intent"),
            "actions": [],
            "candidates": [],
        }
        fallback_used = True
    if len(tx_plan.get("candidates") or []) > max_candidates:
        planner_warnings.append("repair plan exceeded candidate limit; converted to noop")
        tx_plan = {
            "plan_version": 1,
            "type": "noop",
            "reason": "repair output exceeded candidate limit",
            "normalized_intent": state.artifacts.get("normalized_intent"),
            "actions": [],
            "candidates": [],
        }
        fallback_used = True

    previous_plan = state.artifacts.get("tx_plan")
    if previous_plan:
        history = state.artifacts.get("tx_plan_history")
        if not isinstance(history, list):
            history = []
        history.append({"attempt": max(state.attempt - 1, 1), "tx_plan": previous_plan})
        state.artifacts["tx_plan_history"] = history

    state.artifacts["tx_plan"] = tx_plan

    if planner_warnings:
        state.artifacts["repair_planner_warnings"] = planner_warnings
    if fallback_used:
        state.artifacts["repair_planner_fallback"] = {"used": True, "error": llm_error}
    if llm_error:
        state.artifacts["repair_planner_llm_error"] = llm_error
    state.artifacts["repair_planner_llm_used"] = llm_used

    risk_items = [
        RiskItem(severity="MED", title="Repair planner warning", detail=warning)
        for warning in planner_warnings
    ]
    summary = (
        "Repair planner returned a noop plan."
        if tx_plan.get("type") == "noop"
        else "Repair planner produced a transaction plan."
    )
    if fallback_used:
        summary = f"{summary} Fallback planner was used."
    status = "WARN" if planner_warnings or fallback_used else "OK"
    errors = [llm_error] if llm_error else None

    previous_result = state.artifacts.get("planner_result")
    if previous_result:
        result_history = state.artifacts.get("planner_result_history")
        if not isinstance(result_history, list):
            result_history = []
        result_history.append({"attempt": max(state.attempt - 1, 1), "planner_result": previous_result})
        state.artifacts["planner_result_history"] = result_history

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
        sources=["judge_result", "tx_plan", "simulation"],
        errors=errors,
    ).to_public_dict()

    put_artifact(state, "planner_result", planner_result)
    planner_event = agent_result_to_timeline(planner_result)
    planner_event["attempt"] = state.attempt
    append_timeline_event(state, planner_event)

    log_step(
        db,
        run_id=state.run_id,
        step_name="REPAIR_PLAN_TX",
        status="DONE",
        output={
            "attempt": state.attempt,
            "tx_plan": tx_plan,
            "planner_warnings": planner_warnings,
            "llm_error": llm_error,
            "llm_used": llm_used,
        },
        agent="LangGraph",
    )

    return state
```

### CLARIFY

Path: `graph/nodes/clarify.py`

```python
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from db.repos.run_steps_repo import log_step
from graph.state import RunState

_QUESTION_MAP = {
    "wallet_address": "Which wallet address should I use?",
    "chain_id": "Which network (chain) should I use?",
    "amount": "How much should I use?",
    "token_in": "Which token do you want to send or swap from?",
    "token_out": "Which token do you want to receive?",
    "recipient": "Who is the recipient address?",
    "intent": "What would you like to do?",
}


def _question_for(slot: str) -> str:
    if slot in _QUESTION_MAP:
        return _QUESTION_MAP[slot]
    return f"Please provide {slot}."


def clarify(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    log_step(
        db,
        run_id=state.run_id,
        step_name="CLARIFY",
        status="STARTED",
        input={"needs_input": state.artifacts.get("needs_input")},
        agent="LangGraph",
    )

    needs = state.artifacts.get("needs_input")
    if not isinstance(needs, dict):
        log_step(
            db,
            run_id=state.run_id,
            step_name="CLARIFY",
            status="DONE",
            output={"skipped": True},
            agent="LangGraph",
        )
        return state

    questions = needs.get("questions") or []
    if not questions:
        missing = needs.get("missing") or []
        if isinstance(missing, list):
            questions = [_question_for(item) for item in missing]
        needs["questions"] = questions
        state.artifacts["needs_input"] = needs

    log_step(
        db,
        run_id=state.run_id,
        step_name="CLARIFY",
        status="DONE",
        output={"questions": questions},
        agent="LangGraph",
    )
    return state
```

### FINALIZE

Path: `graph/nodes/finalize.py`

```python
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.config import get_settings
from app.contracts.agent_result import AgentResult, Explanation
from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event, agent_result_to_timeline, put_artifact
from graph.state import RunState
from llm.client import LLMClient
from llm.prompts import build_finalize_prompt
from tools.tool_runner import run_tool


def _short_address(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    if len(value) <= 12:
        return value
    return f"{value[:6]}...{value[-4:]}"


def _compact_policy(policy_result: dict | None) -> dict | None:
    if not isinstance(policy_result, dict):
        return None
    checks = policy_result.get("checks") or []
    if not isinstance(checks, list):
        checks = []
    summary = {"pass": 0, "warn": 0, "fail": 0}
    for check in checks:
        status = (check.get("status") or "").upper()
        if status == "PASS":
            summary["pass"] += 1
        elif status == "WARN":
            summary["warn"] += 1
        elif status == "FAIL":
            summary["fail"] += 1
    top_issues = [
        {"title": c.get("title"), "reason": c.get("reason")}
        for c in checks
        if (c.get("status") or "").upper() in {"WARN", "FAIL"}
    ][:3]
    return {"summary": summary, "issues": top_issues}


def _compact_decision(decision: dict | None) -> dict | None:
    if not isinstance(decision, dict):
        return None
    return {
        "action": decision.get("action"),
        "summary": decision.get("summary"),
        "reasons": (decision.get("reasons") or [])[:3],
    }


def _compact_security(security_result: dict | None) -> dict | None:
    if not isinstance(security_result, dict):
        return None
    explanation = security_result.get("explanation") or {}
    return {
        "status": security_result.get("status"),
        "summary": explanation.get("summary"),
    }


def _compact_judge(judge_result: dict | None) -> dict | None:
    if not isinstance(judge_result, dict):
        return None
    output = judge_result.get("output") or {}
    issues = output.get("issues") or []
    first_issue = issues[0] if isinstance(issues, list) and issues else None
    if isinstance(first_issue, dict):
        issue_summary = {
            "code": first_issue.get("code"),
            "message": first_issue.get("message"),
            "severity": first_issue.get("severity"),
        }
    else:
        issue_summary = None
    return {
        "verdict": output.get("verdict"),
        "reasoning_summary": output.get("reasoning_summary"),
        "issue": issue_summary,
    }


def _compact_simulation(simulation: dict | None) -> dict | None:
    if not isinstance(simulation, dict):
        return None
    summary = simulation.get("summary") or {}
    return {
        "status": simulation.get("status"),
        "reason": simulation.get("reason"),
        "num_success": summary.get("num_success"),
        "num_failed": summary.get("num_failed"),
    }


def _compact_tx_requests(tx_requests: list | None) -> dict | None:
    if not isinstance(tx_requests, list):
        return None
    first = tx_requests[0] if tx_requests else None
    if isinstance(first, dict):
        first_summary = {
            "to": _short_address(first.get("to")),
            "valueWei": first.get("valueWei") or first.get("value_wei") or first.get("value"),
            "chainId": first.get("chainId") or first.get("chain_id"),
        }
    else:
        first_summary = None
    return {"count": len(tx_requests), "first": first_summary}


def _is_blocked(artifacts: dict) -> bool:
    decision = artifacts.get("decision") or {}
    action = (decision.get("action") or "").upper()
    if action == "BLOCK":
        return True
    security_result = artifacts.get("security_result") or {}
    if (security_result.get("status") or "").upper() == "BLOCK":
        return True
    judge_result = artifacts.get("judge_result") or {}
    verdict = ((judge_result.get("output") or {}).get("verdict") or "").upper()
    return verdict == "BLOCK"


def _simulation_ok(artifacts: dict) -> bool:
    simulation = artifacts.get("simulation")
    if not isinstance(simulation, dict):
        return False
    if simulation.get("status") == "completed":
        return True
    if simulation.get("success") is True:
        return True
    return False


def _resolve_final_status_suggested(artifacts: dict) -> str:
    if artifacts.get("fatal_error"):
        return "FAILED"
    if artifacts.get("needs_input"):
        return "NEEDS_INPUT"
    if _is_blocked(artifacts):
        return "BLOCKED"
    tx_plan = artifacts.get("tx_plan") or {}
    if isinstance(tx_plan, dict) and tx_plan.get("type") == "noop":
        return "NOOP"
    if not artifacts.get("tx_plan"):
        return "FAILED"
    if not _simulation_ok(artifacts):
        return "FAILED"
    return "READY"


def _fallback_assistant_message(finalize_input: dict) -> str:
    status = (finalize_input.get("final_status") or "FAILED").upper()
    intent = finalize_input.get("normalized_intent") or "your request"
    needs_input = finalize_input.get("needs_input") or {}
    questions = needs_input.get("questions") or []
    if status == "READY":
        return (
            "I prepared a safe transaction plan. Please review and approve to proceed."
            f"\nIntent: {intent}"
        )
    if status == "NEEDS_INPUT":
        if questions:
            lines = "\n".join(f"- {q}" for q in questions)
            return f"I need a bit more detail:\n{lines}"
        return "I need a bit more detail before I can proceed. What would you like to do?"
    if status == "BLOCKED":
        decision = finalize_input.get("decision") or {}
        reason = None
        for item in decision.get("reasons") or []:
            if isinstance(item, str) and item.strip():
                reason = item.strip()
                break
        if reason:
            return f"I can't proceed: {reason}"
        return "I can't proceed: the run was blocked by safety checks. Review the timeline for details."
    if status == "NOOP":
        return (
            "I couldn't identify an action to take. Tell me what you'd like to do, "
            "for example: 'swap 1 USDC to WETH'."
        )
    fatal = finalize_input.get("fatal_error") or {}
    fatal_msg = fatal.get("message") if isinstance(fatal, dict) else None
    if fatal_msg:
        return f"I couldn't complete the request due to an error: {fatal_msg}"
    return "I couldn't complete the request due to an error. Please try again or adjust the request."


def _build_finalize_input(state: RunState) -> dict:
    artifacts = state.artifacts
    tx_plan = artifacts.get("tx_plan") or {}
    tx_requests = artifacts.get("tx_requests") or []
    finalize_input = {
        "normalized_intent": artifacts.get("normalized_intent") or state.intent,
        "final_status": _resolve_final_status_suggested(artifacts),
        "chain_id": state.chain_id,
        "wallet_address": _short_address(state.wallet_address),
        "needs_input": artifacts.get("needs_input"),
        "fatal_error": artifacts.get("fatal_error"),
        "decision": _compact_decision(artifacts.get("decision")),
        "policy_result": _compact_policy(artifacts.get("policy_result")),
        "security_result": _compact_security(artifacts.get("security_result")),
        "judge_result": _compact_judge(artifacts.get("judge_result")),
        "simulation": _compact_simulation(artifacts.get("simulation")),
        "tx_plan": {
            "type": tx_plan.get("type"),
            "reason": tx_plan.get("reason"),
        }
        if isinstance(tx_plan, dict)
        else None,
        "tx_requests": _compact_tx_requests(tx_requests),
    }
    return finalize_input


def _finalize_from_llm(
    *,
    db: Session,
    state: RunState,
    step_id: int,
    finalize_input: dict,
    llm_client: LLMClient,
) -> tuple[str | None, str | None]:
    prompt = build_finalize_prompt(finalize_input)
    raw = run_tool(
        db,
        run_id=state.run_id,
        step_id=step_id,
        tool_name="llm.finalize",
        request={"finalize_input": finalize_input, "prompt": prompt},
        fn=lambda: llm_client.finalize(finalize_input=finalize_input),
    )
    assistant_message = raw.get("assistant_message") if isinstance(raw, dict) else None
    suggested = raw.get("final_status_suggested") if isinstance(raw, dict) else None
    if not isinstance(assistant_message, str) or not assistant_message.strip():
        raise ValueError("finalize assistant_message missing or invalid")
    if isinstance(suggested, str):
        suggested = suggested.strip().upper()
        if suggested not in {"READY", "NEEDS_INPUT", "BLOCKED", "FAILED", "NOOP"}:
            suggested = None
    else:
        suggested = None
    return assistant_message.strip(), suggested


def finalize(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]
    settings = get_settings()

    step = log_step(
        db,
        run_id=state.run_id,
        step_name="FINALIZE",
        status="STARTED",
        input={"artifacts_keys": sorted(list(state.artifacts.keys()))},
        agent="LangGraph",
    )

    if "judge_result" not in state.artifacts:
        judge_result = AgentResult(
            agent="judge",
            step_name="JUDGE_AGENT",
            status="WARN",
            output={
                "verdict": "NEEDS_REWORK",
                "reasoning_summary": "Judge result missing; manual review required.",
                "issues": [],
            },
            explanation=Explanation(
                summary="Judge result missing; manual review required.",
                assumptions=[],
                why_safe=[],
                risks=[],
                next_steps=[],
            ),
            confidence=None,
            sources=["policy_result", "decision", "simulation"],
            errors=None,
        ).to_public_dict()
        put_artifact(state, "judge_result", judge_result)
        judge_event = agent_result_to_timeline(judge_result)
        judge_event["attempt"] = state.attempt
        append_timeline_event(state, judge_event)

    finalize_input = _build_finalize_input(state)
    assistant_message = None
    final_status_suggested = None
    llm_used = False
    llm_error = None

    if settings.LLM_ENABLED:
        llm_client = LLMClient(
            model=settings.LLM_MODEL,
            provider=settings.LLM_PROVIDER,
            api_key=settings.OPENAI_API_KEY,
            temperature=settings.LLM_CHAT_TEMPERATURE,
            timeout_s=settings.LLM_TIMEOUT_S,
        )
        try:
            assistant_message, final_status_suggested = _finalize_from_llm(
                db=db,
                state=state,
                step_id=step.id,
                finalize_input=finalize_input,
                llm_client=llm_client,
            )
            llm_used = True
        except Exception as e:
            llm_error = f"{type(e).__name__}: {e}"

    if not assistant_message:
        assistant_message = _fallback_assistant_message(finalize_input)
        if not final_status_suggested:
            final_status_suggested = finalize_input.get("final_status")

    state.artifacts["assistant_message"] = assistant_message
    if final_status_suggested:
        state.artifacts["final_status_suggested"] = final_status_suggested
    state.artifacts["finalize_summary"] = {
        "final_status_suggested": final_status_suggested,
        "llm_used": llm_used,
        "llm_error": llm_error,
    }

    log_step(
        db,
        run_id=state.run_id,
        step_name="FINALIZE",
        status="DONE",
        output={
            "assistant_message": assistant_message,
            "final_status_suggested": final_status_suggested,
            "llm_used": llm_used,
            "llm_error": llm_error,
        },
        agent="LangGraph",
    )
    return state
```

## Change log

- 2026-01-14: Add PRECHECK/CLARIFY and update FINALIZE snippet.
