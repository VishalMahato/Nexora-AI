from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from db.utils.time import utcnow

from db.base import Base


class RunStatus(enum.Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED_READY = "APPROVED_READY"
    SUBMITTED = "SUBMITTED"
 
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    intent: Mapped[str] = mapped_column(String, nullable=False)
    wallet_address: Mapped[str] = mapped_column(String, nullable=False)
    chain_id: Mapped[int] = mapped_column(nullable=False)

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=RunStatus.CREATED.value,
    )

    error_code: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    artifacts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )

    updated_at = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
