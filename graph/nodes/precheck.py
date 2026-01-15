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

    step = log_step(
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
