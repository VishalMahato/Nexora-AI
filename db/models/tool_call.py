from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.utils.json_type import JSONType
from db.utils.uuid_type import UUIDType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        primary_key=True,
        default=uuid.uuid4,
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    step_id: Mapped[uuid.UUID | None] = mapped_column(      
        UUIDType,
        ForeignKey("run_steps.id", ondelete="SET NULL"),
        nullable=True,
    )

    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)

    request: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )

    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
