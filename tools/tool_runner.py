from __future__ import annotations

from typing import Any, Callable, TypeVar

from sqlalchemy.orm import Session

from db.repos.tool_calls_repo import start_tool_call, finish_tool_call

T = TypeVar("T")


def run_tool(
    db: Session,
    *,
    run_id,
    step_id,
    tool_name: str,
    request: Any,
    fn: Callable[[], T],
) -> T:
    """
    Generic tool execution wrapper.

    - Records start via start_tool_call
    - Executes fn()
    - Records finish via finish_tool_call
    - Re-raises exceptions after logging
    """
    tool_call = start_tool_call(
        db,
        run_id=run_id,
        step_id=step_id,
        tool_name=tool_name,
        request=request,
    )

    try:
        result = fn()
    except Exception as e:
        finish_tool_call(
            db,
            tool_call_id=tool_call.id,
            error=str(e),
        )
        raise

    finish_tool_call(
        db,
        tool_call_id=tool_call.id,
        response=result,
    )
    return result
