from __future__ import annotations

from fastapi import HTTPException

from app.domain.final_status import FinalStatus


def ensure_final_status_ready(*, run, action: str) -> None:
    final_status = (getattr(run, "final_status", None) or "").upper()
    if final_status == FinalStatus.READY.value:
        return

    reason = _final_status_reason(final_status, action=action)
    status_label = getattr(run, "status", None) or "UNKNOWN"
    final_label = final_status or "UNKNOWN"
    detail = f"cannot {action}: {reason} (final_status={final_label}, status={status_label})"
    raise HTTPException(status_code=409, detail=detail)


def _final_status_reason(final_status: str, *, action: str) -> str:
    if final_status == FinalStatus.NEEDS_INPUT.value:
        return "missing required info"
    if final_status == FinalStatus.BLOCKED.value:
        return "run is blocked"
    if final_status == FinalStatus.FAILED.value:
        return "run failed"
    if final_status == FinalStatus.NOOP.value:
        return "nothing to approve" if action == "approve" else "nothing to execute"
    return "run not ready"
