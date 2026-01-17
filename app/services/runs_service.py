from __future__ import annotations

from uuid import UUID
import re

from sqlalchemy.orm import Session

from app.domain.final_status import FinalStatus
from db.models.run import RunStatus
from db.repos.run_steps_repo import log_step
from db.repos.tool_calls_repo import log_tool_call
from db.repos.runs_repo import (
    RunNotFoundError,
    RunStatusConflictError,
    create_run,
    finalize_run,
    get_run,
    update_run_artifacts,
    update_run_status,
)
from graph.checkpointing import get_checkpointer
from graph.graph import build_graph, run_graph
from graph.state import RunState
from graph.utils.needs_input import clear_needs_input


def create_run_with_audit(
    *,
    db: Session,
    intent: str,
    wallet_address: str,
    chain_id: int,
    agent: str,
    tool_name: str,
) -> UUID:
    run = create_run(
        db,
        intent=intent,
        wallet_address=wallet_address,
        chain_id=chain_id,
    )

    created_step = log_step(
        db,
        run_id=run.id,
        step_name="RUN_CREATED",
        status="DONE",
        output={"status": run.status},
        agent=agent,
    )

    log_tool_call(
        db,
        run_id=run.id,
        step_id=created_step.id,
        tool_name=tool_name,
        request={
            "intent": intent,
            "walletAddress": wallet_address,
            "chainId": chain_id,
        },
        response={"run_id": str(run.id)},
    )

    return run.id


def _is_blocked(artifacts: dict) -> bool:
    decision = artifacts.get("decision") or {}
    action = (decision.get("action") or "").upper()
    if action == "BLOCK":
        return True

    security_result = artifacts.get("security_result") or {}
    security_status = (security_result.get("status") or "").upper()
    if security_status == "BLOCK":
        return True

    judge_result = artifacts.get("judge_result") or {}
    verdict = ((judge_result.get("output") or {}).get("verdict") or "").upper()
    return verdict == "BLOCK"


def _is_noop_plan(artifacts: dict) -> bool:
    tx_plan = artifacts.get("tx_plan") or {}
    return isinstance(tx_plan, dict) and tx_plan.get("type") == "noop"


def _simulation_ok(artifacts: dict) -> bool:
    simulation = artifacts.get("simulation")
    if not isinstance(simulation, dict):
        return False
    if simulation.get("status") == "completed":
        return True
    if simulation.get("success") is True:
        return True
    return False


def _resolve_final_status(artifacts: dict) -> FinalStatus:
    if artifacts.get("fatal_error"):
        return FinalStatus.FAILED

    if artifacts.get("needs_input"):
        return FinalStatus.NEEDS_INPUT

    if _is_blocked(artifacts):
        return FinalStatus.BLOCKED

    if _is_noop_plan(artifacts):
        return FinalStatus.NOOP

    if not artifacts.get("tx_plan"):
        return FinalStatus.FAILED

    if not _simulation_ok(artifacts):
        return FinalStatus.FAILED

    return FinalStatus.READY


def _map_run_status(final_status: FinalStatus) -> RunStatus:
    if final_status == FinalStatus.READY:
        return RunStatus.AWAITING_APPROVAL
    if final_status == FinalStatus.BLOCKED:
        return RunStatus.BLOCKED
    if final_status == FinalStatus.FAILED:
        return RunStatus.FAILED
    if final_status in {FinalStatus.NEEDS_INPUT, FinalStatus.NOOP}:
        return RunStatus.PAUSED
    return RunStatus.FAILED


_SWAP_PATTERN = re.compile(
    r"^swap(?:\s+([0-9]+(?:\.[0-9]+)?))?(?:\s+([a-zA-Z0-9]+))?(?:\s+to\s+([a-zA-Z0-9]+))?$"
)
_TRANSFER_PATTERN = re.compile(
    r"^(send|transfer)(?:\s+([0-9]+(?:\.[0-9]+)?))?(?:\s+([a-zA-Z0-9]+))?(?:\s+to\s+(0x[a-fA-F0-9]{40}))?$"
)


def _extract_answer(answers: dict, *keys: str) -> str | None:
    for key in keys:
        value = answers.get(key)
        if value is None:
            continue
        value_str = str(value).strip()
        if value_str:
            return value_str
    return None


def _build_swap_intent(base_intent: str, answers: dict) -> str | None:
    text = " ".join(base_intent.lower().split())
    match = _SWAP_PATTERN.match(text)
    if not match:
        return None
    amount = _extract_answer(answers, "amount_in", "amount")
    token_in = _extract_answer(answers, "token_in", "tokenIn")
    token_out = _extract_answer(answers, "token_out", "tokenOut")
    if not amount:
        amount = match.group(1)
    if not token_in:
        token_in = match.group(2)
    if not token_out:
        token_out = match.group(3)
    if not (amount and token_in and token_out):
        return None
    return f"swap {amount} {token_in} to {token_out}"


def _build_transfer_intent(base_intent: str, answers: dict) -> str | None:
    text = " ".join(base_intent.lower().split())
    match = _TRANSFER_PATTERN.match(text)
    action = match.group(1) if match else None
    action = _extract_answer(answers, "action") or action or "send"
    amount = _extract_answer(answers, "amount")
    asset = _extract_answer(answers, "asset", "token", "token_in")
    recipient = _extract_answer(answers, "recipient", "to", "to_address")
    if not amount and match:
        amount = match.group(2)
    if not asset and match:
        asset = match.group(3)
    if not recipient and match:
        recipient = match.group(4)
    if not (amount and asset and recipient):
        return None
    return f"{action} {amount} {asset} to {recipient}"


def _apply_resume_answers(state: RunState, answers: dict, metadata: dict | None) -> None:
    artifacts = state.artifacts
    user_inputs = artifacts.get("user_inputs")
    if not isinstance(user_inputs, dict):
        user_inputs = {}
    user_inputs.update(answers)
    artifacts["user_inputs"] = user_inputs
    if metadata:
        artifacts["resume_metadata"] = metadata

    wallet = _extract_answer(answers, "wallet_address", "walletAddress")
    if wallet:
        state.wallet_address = wallet

    chain = _extract_answer(answers, "chain_id", "chainId")
    if chain:
        try:
            state.chain_id = int(chain)
        except ValueError:
            pass

    direct_intent = _extract_answer(answers, "normalized_intent", "intent", "message")
    base_intent = direct_intent or artifacts.get("normalized_intent") or state.intent
    base_intent = str(base_intent or "").strip()
    next_intent = None
    if direct_intent:
        next_intent = base_intent
    elif base_intent.lower().startswith("swap"):
        next_intent = _build_swap_intent(base_intent, answers)
    elif base_intent.lower().startswith("send") or base_intent.lower().startswith("transfer"):
        next_intent = _build_transfer_intent(base_intent, answers)

    if next_intent:
        artifacts["normalized_intent"] = next_intent
        state.intent = next_intent


def _load_checkpoint_state(*, run_id: UUID) -> RunState | None:
    app = build_graph().compile(checkpointer=get_checkpointer())
    snapshot = app.get_state({"configurable": {"thread_id": str(run_id)}})
    values = snapshot.values
    if not isinstance(values, dict) or not values:
        return None
    if "run_id" not in values:
        return None
    return RunState.model_validate(values)


def start_run_sync(*, db: Session, run_id: UUID) -> dict:
    run = get_run(db, run_id)
    if not run:
        raise RunNotFoundError("Run not found")

    if RunStatus(run.status) != RunStatus.CREATED:
        raise RunStatusConflictError(f"Run cannot be started from status={run.status}")

    update_run_status(
        db,
        run_id=run_id,
        to_status=RunStatus.RUNNING,
        expected_from=RunStatus.CREATED,
    )

    artifacts: dict = {}
    try:
        state = RunState(
            run_id=run.id,
            intent=run.intent,
            status=RunStatus.RUNNING,
            chain_id=run.chain_id,
            wallet_address=run.wallet_address,
        )

        final_state = run_graph(db, state)

        artifacts = (
            final_state.artifacts
            if hasattr(final_state, "artifacts")
            else final_state.get("artifacts", {})
        )

        final_status = _resolve_final_status(artifacts)
        run_status = _map_run_status(final_status)

        finalize_run(
            db,
            run_id=run_id,
            artifacts=artifacts,
            to_status=run_status,
            expected_from=RunStatus.RUNNING,
            final_status=final_status.value,
        )

        return {
            "ok": True,
            "runId": str(run.id),
            "status": run_status.value,
            "final_status": final_status.value,
            "artifacts": artifacts,
        }
    except Exception as e:
        try:
            if artifacts:
                update_run_artifacts(db, run_id=run_id, artifacts=artifacts)
        except Exception:
            pass
        try:
            update_run_status(
                db,
                run_id=run_id,
                to_status=RunStatus.FAILED,
                expected_from=RunStatus.RUNNING,
                error_code="GRAPH_EXECUTION_ERROR",
                error_message=f"{type(e).__name__}: {e}",
                final_status=FinalStatus.FAILED.value,
            )
        except Exception:
            pass
        raise RuntimeError(f"Run execution failed: {type(e).__name__}: {e}") from e


def resume_run_sync(
    *,
    db: Session,
    run_id: UUID,
    answers: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    run = get_run(db, run_id)
    if not run:
        raise RunNotFoundError("Run not found")

    if RunStatus(run.status) != RunStatus.PAUSED:
        raise RunStatusConflictError(f"Run cannot be resumed from status={run.status}")

    if run.final_status != FinalStatus.NEEDS_INPUT.value and not (run.artifacts or {}).get("needs_input"):
        raise RunStatusConflictError("Run is not waiting for input")

    state = _load_checkpoint_state(run_id=run_id)
    if not state:
        raise RunStatusConflictError("No checkpoint found for this run")

    answers = answers or {}
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object")

    _apply_resume_answers(state, answers, metadata)
    clear_needs_input(state)
    state.status = RunStatus.RUNNING

    update_run_status(
        db,
        run_id=run_id,
        to_status=RunStatus.RUNNING,
        expected_from=RunStatus.PAUSED,
    )

    artifacts: dict = {}
    try:
        final_state = run_graph(db, state)
        artifacts = (
            final_state.artifacts
            if hasattr(final_state, "artifacts")
            else final_state.get("artifacts", {})
        )
        final_status = _resolve_final_status(artifacts)
        run_status = _map_run_status(final_status)
        finalize_run(
            db,
            run_id=run_id,
            artifacts=artifacts,
            to_status=run_status,
            expected_from=RunStatus.RUNNING,
            final_status=final_status.value,
        )
        return {
            "ok": True,
            "runId": str(run.id),
            "status": run_status.value,
            "final_status": final_status.value,
            "artifacts": artifacts,
        }
    except Exception as e:
        try:
            if artifacts:
                update_run_artifacts(db, run_id=run_id, artifacts=artifacts)
        except Exception:
            pass
        try:
            update_run_status(
                db,
                run_id=run_id,
                to_status=RunStatus.FAILED,
                expected_from=RunStatus.RUNNING,
                error_code="GRAPH_EXECUTION_ERROR",
                error_message=f"{type(e).__name__}: {e}",
                final_status=FinalStatus.FAILED.value,
            )
        except Exception:
            pass
        raise RuntimeError(f"Run resume failed: {type(e).__name__}: {e}") from e
