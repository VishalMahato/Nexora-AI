from __future__ import annotations

from app.domain.final_status import FinalStatus
from db.models.run import RunStatus
from app.services import runs_service


def test_final_status_fatal_error():
    artifacts = {"fatal_error": {"step": "PLAN_TX"}}
    assert runs_service._resolve_final_status(artifacts) == FinalStatus.FAILED


def test_final_status_needs_input():
    artifacts = {"needs_input": {"questions": ["wallet_address"]}}
    assert runs_service._resolve_final_status(artifacts) == FinalStatus.NEEDS_INPUT


def test_final_status_blocked():
    artifacts = {"decision": {"action": "BLOCK"}}
    assert runs_service._resolve_final_status(artifacts) == FinalStatus.BLOCKED


def test_final_status_noop():
    artifacts = {"tx_plan": {"type": "noop"}}
    assert runs_service._resolve_final_status(artifacts) == FinalStatus.NOOP


def test_final_status_ready():
    artifacts = {"tx_plan": {"type": "plan"}, "simulation": {"status": "completed"}}
    assert runs_service._resolve_final_status(artifacts) == FinalStatus.READY


def test_map_run_status_ready_only():
    assert runs_service._map_run_status(FinalStatus.READY) == RunStatus.AWAITING_APPROVAL
    assert runs_service._map_run_status(FinalStatus.NEEDS_INPUT) == RunStatus.PAUSED
    assert runs_service._map_run_status(FinalStatus.NOOP) == RunStatus.PAUSED
