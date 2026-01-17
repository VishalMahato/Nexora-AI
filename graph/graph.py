from __future__ import annotations

import os
from typing import Optional, List, Any

from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from graph.state import RunState
from graph.checkpointing import get_checkpointer
from graph.nodes import (
    input_normalize,
    precheck,
    wallet_snapshot,
    plan_tx,
    build_txs,
    simulate_txs,
    policy_eval,
    security_eval,
    judge_agent,
    repair_router,
    repair_plan_tx,
    clarify,
    finalize,
)
from graph.utils.routing import route_post_step


def build_graph() -> StateGraph:
    """
    INPUT_NORMALIZE -> PRECHECK -> WALLET_SNAPSHOT -> PLAN_TX -> BUILD_TXS
    -> SIMULATE_TXS -> POLICY_EVAL -> SECURITY_EVAL -> JUDGE_AGENT -> REPAIR_ROUTER
    -> (REPAIR_PLAN_TX -> BUILD_TXS -> SIMULATE_TXS -> POLICY_EVAL -> SECURITY_EVAL -> JUDGE_AGENT) -> FINALIZE -> END
    """
    graph = StateGraph(RunState)

    graph.add_node("INPUT_NORMALIZE", input_normalize)
    graph.add_node("PRECHECK", precheck)
    graph.add_node("WALLET_SNAPSHOT", wallet_snapshot)
    graph.add_node("PLAN_TX", plan_tx)
    graph.add_node("BUILD_TXS", build_txs)
    graph.add_node("SIMULATE_TXS", simulate_txs)
    graph.add_node("POLICY_EVAL", policy_eval)
    graph.add_node("SECURITY_EVAL", security_eval)
    graph.add_node("JUDGE_AGENT", judge_agent)
    graph.add_node("REPAIR_ROUTER", repair_router)
    graph.add_node("REPAIR_PLAN_TX", repair_plan_tx)
    graph.add_node("CLARIFY", clarify)
    graph.add_node("FINALIZE", finalize)

    graph.set_entry_point("INPUT_NORMALIZE")

    def route_or_finalize(next_step: str):
        def _route(state: RunState) -> str:
            return route_post_step(state, default_next=next_step)
        return _route

    graph.add_conditional_edges(
        "INPUT_NORMALIZE",
        route_or_finalize("PRECHECK"),
        {
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
            "PRECHECK": "PRECHECK",
        },
    )
    graph.add_conditional_edges(
        "PRECHECK",
        route_or_finalize("WALLET_SNAPSHOT"),
        {
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
            "WALLET_SNAPSHOT": "WALLET_SNAPSHOT",
        },
    )

    # ✅ INSERT PLAN_TX in the pipeline
    graph.add_conditional_edges(
        "WALLET_SNAPSHOT",
        route_or_finalize("PLAN_TX"),
        {
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
            "PLAN_TX": "PLAN_TX",
        },
    )
    def route_after_plan_tx(state: RunState) -> str:
        routed = route_post_step(state, default_next="BUILD_TXS")
        if routed != "BUILD_TXS":
            return routed
        artifacts = state.artifacts or {}
        tx_plan = artifacts.get("tx_plan") or {}
        if isinstance(tx_plan, dict):
            if tx_plan.get("type") == "noop":
                return "FINALIZE"
            actions = tx_plan.get("actions") or []
            candidates = tx_plan.get("candidates") or []
            if not actions and not candidates:
                return "FINALIZE"
        return "BUILD_TXS"

    graph.add_conditional_edges(
        "PLAN_TX",
        route_after_plan_tx,
        {
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
            "BUILD_TXS": "BUILD_TXS",
        },
    )
    graph.add_conditional_edges(
        "BUILD_TXS",
        route_or_finalize("SIMULATE_TXS"),
        {
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
            "SIMULATE_TXS": "SIMULATE_TXS",
        },
    )
    graph.add_conditional_edges(
        "SIMULATE_TXS",
        route_or_finalize("POLICY_EVAL"),
        {
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
            "POLICY_EVAL": "POLICY_EVAL",
        },
    )
    graph.add_conditional_edges(
        "POLICY_EVAL",
        route_or_finalize("SECURITY_EVAL"),
        {
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
            "SECURITY_EVAL": "SECURITY_EVAL",
        },
    )
    graph.add_conditional_edges(
        "SECURITY_EVAL",
        route_or_finalize("JUDGE_AGENT"),
        {
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
            "JUDGE_AGENT": "JUDGE_AGENT",
        },
    )
    graph.add_conditional_edges(
        "JUDGE_AGENT",
        route_or_finalize("REPAIR_ROUTER"),
        {
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
            "REPAIR_ROUTER": "REPAIR_ROUTER",
        },
    )

    def route_repair(state: RunState) -> str:
        next_step = state.artifacts.get("repair_next_step", "FINALIZE")
        return route_post_step(state, default_next=next_step)

    graph.add_conditional_edges(
        "REPAIR_ROUTER",
        route_repair,
        {
            "REPAIR_PLAN_TX": "REPAIR_PLAN_TX",
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
        },
    )

    graph.add_conditional_edges(
        "REPAIR_PLAN_TX",
        route_or_finalize("BUILD_TXS"),
        {
            "CLARIFY": "CLARIFY",
            "FINALIZE": "FINALIZE",
            "BUILD_TXS": "BUILD_TXS",
        },
    )
    graph.add_edge("CLARIFY", "FINALIZE")
    graph.add_edge("FINALIZE", END)

    return graph


def _langsmith_callbacks() -> Optional[List[Any]]:
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() not in {"true", "1", "yes"}:
        return None

    try:
        from langchain_core.tracers.langchain import LangChainTracer
    except Exception:
        return None

    tracer = LangChainTracer(project_name=os.getenv("LANGCHAIN_PROJECT"))
    return [tracer]


def run_graph(db: Session, state: RunState) -> RunState:
    graph = build_graph()
    app = graph.compile(checkpointer=get_checkpointer())

    callbacks = _langsmith_callbacks()

    config: dict[str, Any] = {
        "configurable": {"db": db, "thread_id": str(state.run_id)},
        "tags": ["nexora", "langgraph"],
        "metadata": {"run_id": str(state.run_id)},
    }
    if callbacks:
        config["callbacks"] = callbacks

    result = app.invoke(
        state.model_dump(),
        config=config,
    )

    return RunState.model_validate(result)
