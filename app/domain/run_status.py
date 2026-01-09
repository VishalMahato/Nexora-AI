from __future__ import annotations

from db.models.run import RunStatus

TERMINAL = {
    RunStatus.FAILED,
    RunStatus.REJECTED,
    RunStatus.BLOCKED,
}

ALLOWED = {
    RunStatus.CREATED: {RunStatus.RUNNING},
    RunStatus.RUNNING: {RunStatus.AWAITING_APPROVAL, RunStatus.FAILED, RunStatus.BLOCKED},
    RunStatus.AWAITING_APPROVAL: {RunStatus.APPROVED_READY, RunStatus.REJECTED},
    RunStatus.APPROVED_READY: {RunStatus.SUBMITTED},
    RunStatus.SUBMITTED: set(),
    RunStatus.FAILED: set(),
    RunStatus.REJECTED: set(),
    RunStatus.BLOCKED: set(),
}


def assert_valid_transition(frm: RunStatus, to: RunStatus) -> None:
    if frm in TERMINAL:
        raise ValueError(f"Cannot transition from terminal status: {frm.value}")

    if to not in ALLOWED.get(frm, set()):
        raise ValueError(f"Invalid status transition: {frm.value} -> {to.value}")
