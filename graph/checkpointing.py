from __future__ import annotations

import logging
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_checkpointer() -> BaseCheckpointSaver:
    settings = get_settings()
    database_url = settings.DATABASE_URL
    if not database_url:
        logger.warning("DATABASE_URL missing; falling back to in-memory checkpointer.")
        return InMemorySaver()

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except Exception as exc:
        logger.warning(
            "Postgres checkpointer unavailable; falling back to in-memory. Error: %s",
            exc,
        )
        return InMemorySaver()

    checkpointer = PostgresSaver.from_conn_string(database_url)
    try:
        checkpointer.setup()
    except Exception as exc:
        logger.warning("Postgres checkpointer setup failed: %s", exc)
    return checkpointer
