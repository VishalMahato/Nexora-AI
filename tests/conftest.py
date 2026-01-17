import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.config import get_settings


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def _configure_llm(monkeypatch, request):
    monkeypatch.setenv("ALLOWLIST_TO_ALL", "false")
    get_settings.cache_clear()
    if request.node.get_closest_marker("use_llm"):
        yield
        return
    monkeypatch.setenv("LLM_ENABLED", "false")
    get_settings.cache_clear()
    yield
