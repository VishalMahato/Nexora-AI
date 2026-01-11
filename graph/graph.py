from __future__ import annotations

import os
from typing import Optional, List, Any

from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from graph.state import RunState
from graph.nodes import (
    input_normalize,
    wallet_snapshot,
    plan_tx,        
    build_txs,
    simulate_txs,
    policy_eval,
    security_eval,
    judge_agent,
    repair_router,
    repair_plan_tx,
    finalize,
)


def build_graph() -> StateGraph:
    """
    INPUT_NORMALIZE -> WALLET_SNAPSHOT -> PLAN_TX -> BUILD_TXS
    -> SIMULATE_TXS -> POLICY_EVAL -> SECURITY_EVAL -> JUDGE_AGENT -> REPAIR_ROUTER
    -> (REPAIR_PLAN_TX -> BUILD_TXS -> SIMULATE_TXS -> POLICY_EVAL -> SECURITY_EVAL -> JUDGE_AGENT) -> FINALIZE -> END
    """
    graph = StateGraph(RunState)

    graph.add_node("INPUT_NORMALIZE", input_normalize)
    graph.add_node("WALLET_SNAPSHOT", wallet_snapshot)
    graph.add_node("PLAN_TX", plan_tx)          # ✅ ADD
    graph.add_node("BUILD_TXS", build_txs)
    graph.add_node("SIMULATE_TXS", simulate_txs)
    graph.add_node("POLICY_EVAL", policy_eval)
    graph.add_node("SECURITY_EVAL", security_eval)
    graph.add_node("JUDGE_AGENT", judge_agent)
    graph.add_node("REPAIR_ROUTER", repair_router)
    graph.add_node("REPAIR_PLAN_TX", repair_plan_tx)
    graph.add_node("FINALIZE", finalize)

    graph.set_entry_point("INPUT_NORMALIZE")

    graph.add_edge("INPUT_NORMALIZE", "WALLET_SNAPSHOT")

    # ✅ INSERT PLAN_TX in the pipeline
    graph.add_edge("WALLET_SNAPSHOT", "PLAN_TX")
    graph.add_edge("PLAN_TX", "BUILD_TXS")

    graph.add_edge("BUILD_TXS", "SIMULATE_TXS")
    graph.add_edge("SIMULATE_TXS", "POLICY_EVAL")
    graph.add_edge("POLICY_EVAL", "SECURITY_EVAL")
    graph.add_edge("SECURITY_EVAL", "JUDGE_AGENT")
    graph.add_edge("JUDGE_AGENT", "REPAIR_ROUTER")

    def route_repair(state: RunState) -> str:
        return state.artifacts.get("repair_next_step", "FINALIZE")

    graph.add_conditional_edges(
        "REPAIR_ROUTER",
        route_repair,
        {
            "REPAIR_PLAN_TX": "REPAIR_PLAN_TX",
            "FINALIZE": "FINALIZE",
        },
    )

    graph.add_edge("REPAIR_PLAN_TX", "BUILD_TXS")
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
    app = graph.compile()

    callbacks = _langsmith_callbacks()

    config: dict[str, Any] = {
        "configurable": {"db": db},
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
