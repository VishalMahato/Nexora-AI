from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from db.repos.run_steps_repo import log_step
from graph.artifacts import append_timeline_event
from graph.state import RunState

_QUESTION_MAP = {
    "amount_in": "How much do you want to swap?",
    "amount": "How much do you want to transfer?",
    "token_in": "Which token are you swapping from?",
    "token_out": "Which token do you want to receive?",
    "wallet_address": "What wallet address should I use?",
    "chain_id": "Which chain are you using (e.g., Ethereum mainnet)?",
    "recipient": "What recipient address should I use?",
}


def _questions_from_missing(missing: list[str]) -> list[str]:
    questions: list[str] = []
    for slot in missing:
        question = _QUESTION_MAP.get(slot)
        if question:
            questions.append(question)
        else:
            questions.append(f"Please provide {slot}.")
    if not questions:
        questions.append("What additional details can you provide so I can continue?")
    return questions


def clarify(state: RunState, config: RunnableConfig) -> RunState:
    db: Session = config["configurable"]["db"]

    step = log_step(
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
            output={"reason": "needs_input_missing"},
            agent="LangGraph",
        )
        return state

    questions = needs.get("questions") or []
    missing = needs.get("missing") or []
    if not questions:
        questions = _questions_from_missing(missing if isinstance(missing, list) else [])
        needs["questions"] = questions
        state.artifacts["needs_input"] = needs

    summary = "Awaiting user input."
    append_timeline_event(
        state,
        {
            "step": "CLARIFY",
            "status": "DONE",
            "title": "clarify",
            "summary": summary,
            "attempt": state.attempt,
        },
    )

    log_step(
        db,
        run_id=state.run_id,
        step_name="CLARIFY",
        status="DONE",
        output={
            "questions": questions,
            "missing": missing,
            "resume_from": needs.get("resume_from"),
        },
        agent="LangGraph",
    )
    return state
