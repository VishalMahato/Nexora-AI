from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.context import set_run_id


class RunContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        """
        Sets run_id into contextvars for the lifetime of the request.

        Priority:
        1. Path param: /runs/{run_id}
        2. Header: X-Run-Id
        """
        run_id = None

        # 1️⃣ Try to extract from path params
        if "run_id" in request.path_params:
            run_id = request.path_params.get("run_id")

        # 2️⃣ Fallback to header
        if not run_id:
            run_id = request.headers.get("X-Run-Id")

        try:
            if run_id:
                set_run_id(str(run_id))
            response = await call_next(request)
            return response
        finally:
            # 🔥 CRITICAL: always clear context
            set_run_id(None)
