from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from db.session import SessionLocal
from db.models.run import Run
from app.domain.run_status import RunStatus
from db.repos.run_steps_repo import list_steps_for_run
from db.session import SessionLocal


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app)


def _cleanup_run(run_id: uuid.UUID) -> None:
    """Best-effort cleanup to avoid test data piling up in a shared DB."""
    db = SessionLocal()
    try:
        obj = db.get(Run, run_id)
        if obj is not None:
            db.delete(obj)
            db.commit()
    finally:
        db.close()


def test_post_v1_runs_creates_run(client):
    payload = {
        "intent": "Swap 50 USDC to ETH",
        "walletAddress": "0xabc123",
        "chainId": 1,
    }

    resp = client.post("/v1/runs", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert "runId" in data
    assert data["status"] == RunStatus.CREATED.value

    run_id = uuid.UUID(data["runId"])
    _cleanup_run(run_id)


def test_get_v1_runs_returns_run(client):
    # First create a run
    create_payload = {
        "intent": "Check balances",
        "walletAddress": "0xabc123",
        "chainId": 1,
    }

    create_resp = client.post("/v1/runs", json=create_payload)
    assert create_resp.status_code == 200, create_resp.text
    run_id = uuid.UUID(create_resp.json()["runId"])

    # Then fetch it
    get_resp = client.get(f"/v1/runs/{run_id}")
    assert get_resp.status_code == 200, get_resp.text

    body = get_resp.json()
    assert "run" in body
    run = body["run"]

    assert run["id"] == str(run_id)
    assert run["intent"] == create_payload["intent"]
    assert run["wallet_address"] == create_payload["walletAddress"]
    assert run["chain_id"] == create_payload["chainId"]
    assert run["status"] == RunStatus.CREATED.value

    _cleanup_run(run_id)


def test_get_v1_runs_unknown_id_404(client):
    unknown = uuid.uuid4()
    resp = client.get(f"/v1/runs/{unknown}")
    assert resp.status_code == 404

def test_post_v1_runs_creates_initial_step(client):
    payload = {
        "intent": "Swap 50 USDC to ETH",
        "walletAddress": "0xabc123",
        "chainId": 1,
    }

    resp = client.post("/v1/runs", json=payload)
    assert resp.status_code == 200

    run_id = resp.json()["runId"]

    db = SessionLocal()
    try:
        steps = list_steps_for_run(db, run_id=run_id)
        assert len(steps) >= 1
        assert steps[0].step_name == "RUN_CREATED"
    finally:
        db.close()
