from __future__ import annotations

import os
from typing import Optional, List, Any

from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from graph.state import RunState
from graph.nodes import input_normalize, finalize


def build_graph() -> StateGraph:
    """
    Builds the LangGraph skeleton:
    START -> INPUT_NORMALIZE -> FINALIZE -> END
    """
    graph = StateGraph(RunState)

    graph.add_node("INPUT_NORMALIZE", input_normalize)
    graph.add_node("FINALIZE", finalize)

    graph.set_entry_point("INPUT_NORMALIZE")
    graph.add_edge("INPUT_NORMALIZE", "FINALIZE")
    graph.add_edge("FINALIZE", END)

    return graph



def _langsmith_callbacks() -> Optional[List[Any]]:
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() not in {"true", "1", "yes"}:
        return None

    try:
        from langchain_core.tracers.langchain import LangChainTracer
    except Exception:
        # Tracer not available in this environment; do not crash
        return None

    tracer = LangChainTracer(
        project_name=os.getenv("LANGCHAIN_PROJECT")
    )
    return [tracer]


def run_graph(db: Session, state: RunState) -> RunState:
    graph = build_graph()
    app = graph.compile()

    callbacks = _langsmith_callbacks()

    config: dict[str, Any] = {
        "configurable": {"db": db},
        # Helps you filter/search runs in LangSmith
        "tags": ["nexora", "langgraph"],
        "metadata": {"run_id": str(state.run_id)},
    }
    if callbacks:
        config["callbacks"] = callbacks

    result = app.invoke(
        state.model_dump(),  # ✅ pass dict in
        config=config,
    )

    # ✅ ensure we return RunState
    return RunState.model_validate(result)
