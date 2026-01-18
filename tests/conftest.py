import os
import pytest
from fastapi.testclient import TestClient

# Set test database before any imports
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from app.main import create_app
from app.config import get_settings
from db.base import Base
from db.session import engine


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables before tests run, drop after all tests complete."""
    # Import models to ensure they are registered with Base
    from db.models import Run, RunStep, ToolCall  # noqa: F401
    
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_tables():
    """Clean tables between tests to ensure isolation."""
    yield
    # After each test, clean up
    from db.session import SessionLocal
    from db.models import Run, RunStep, ToolCall
    
    with SessionLocal() as db:
        db.query(ToolCall).delete()
        db.query(RunStep).delete()
        db.query(Run).delete()
        db.commit()


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
