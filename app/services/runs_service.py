from __future__ import annotations

from uuid import UUID

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
from graph.graph import run_graph
from graph.state import RunState


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
