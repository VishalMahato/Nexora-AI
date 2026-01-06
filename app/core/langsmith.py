from __future__ import annotations

import os

from app.config import get_settings


def configure_langsmith() -> None:
    s = get_settings()

    if not s.langsmith_tracing:
        return

    # LangChain/LangSmith standard env vars
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if s.langsmith_api_key:
        os.environ["LANGCHAIN_API_KEY"] = s.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = s.langsmith_project
    os.environ["LANGCHAIN_ENDPOINT"] = s.langsmith_endpoint
