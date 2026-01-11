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
            "allowlisted_tokens": getattr(settings, "allowlisted_tokens", {}) or {},
            "allowlisted_routers": getattr(settings, "allowlisted_routers", {}) or {},
            "defaults": getattr(settings, "defaults", {}) or {},
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
