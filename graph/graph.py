from __future__ import annotations

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


def run_graph(db: Session, state: RunState) -> RunState:
    graph = build_graph()
    app = graph.compile()

    result = app.invoke(
        state.model_dump(),  # ✅ pass dict in
        config={"configurable": {"db": db}},
    )

    # ✅ ensure we return RunState
    return RunState.model_validate(result)

