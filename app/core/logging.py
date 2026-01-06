from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.context import get_run_id
from app.config import get_settings


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = get_run_id() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": utc_iso(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "run_id": getattr(record, "run_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = utc_iso()
        run_id = getattr(record, "run_id", "-")
        base = f"{ts} {record.levelname:<7} run_id={run_id} {record.name}: {record.getMessage()}"
        if record.exc_info:
            return base + "\n" + self.formatException(record.exc_info)
        return base


def configure_logging() -> None:
    settings = get_settings()

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RunIdFilter())

    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root.addHandler(handler)

    # noise control (optional)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
