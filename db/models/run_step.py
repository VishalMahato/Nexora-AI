from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.utils.json_type import JSONType
from db.utils.uuid_type import UUIDType


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStep(Base):
    __tablename__ = "run_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    step_name: Mapped[str] = mapped_column(String(64), nullable=False)
    agent: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False)

    input: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


    # # Helpful composite indexes for timeline queries
    # Index("idx_run_steps_run_id_started_at", RunStep.run_id, RunStep.started_at)
    # Index("idx_run_steps_run_id_step_name", RunStep.run_id, RunStep.step_name)
