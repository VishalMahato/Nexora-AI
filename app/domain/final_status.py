from __future__ import annotations

from enum import Enum


class FinalStatus(str, Enum):
    READY = "READY"
    NEEDS_INPUT = "NEEDS_INPUT"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    NOOP = "NOOP"
