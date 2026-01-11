from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_app_starts_without_langsmith_env(monkeypatch):
    """
    LangSmith must be OPTIONAL.
    App should start even if tracing env vars are missing.
    """
    # Remove LangSmith-related env vars (if present)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_PROJECT", raising=False)
    monkeypatch.delenv("LANGCHAIN_ENDPOINT", raising=False)

    app = create_app()
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200


def test_app_starts_when_langsmith_disabled(monkeypatch):
    """
    Even if env vars exist, when tracing is disabled, app must not crash.
    """
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.setenv("LANGCHAIN_PROJECT", "nexora-ai-test")
    monkeypatch.setenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")

    app = create_app()
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 200
