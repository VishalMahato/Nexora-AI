from __future__ import annotations

import uuid
from unittest.mock import patch

from app.chat.contracts import IntentMode


def test_chat_action_creates_and_starts_run(client):
    run_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")

    with (
        patch(
            "app.chat.router.classify_intent",
            return_value={
                "mode": "ACTION",
                "intent_type": "SWAP",
                "confidence": 0.9,
                "slots": {"token_in": "USDC", "token_out": "WETH", "amount_in": "1"},
                "missing_slots": [],
                "reason": "actionable swap",
            },
        ),
        patch("app.chat.router.create_run_from_action", return_value=run_id) as create_run,
        patch("app.chat.router.start_run_for_action", return_value={"status": "AWAITING_APPROVAL"}) as start_run,
    ):
        resp = client.post(
            "/v1/chat/route",
            json={
                "message": "swap 1 usdc to weth",
                "wallet_address": "0x1111111111111111111111111111111111111111",
                "chain_id": 1,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.ACTION.value
    assert body["run_id"] == str(run_id)
    assert body["run_ref"]["status"] == "AWAITING_APPROVAL"
    create_run.assert_called_once()
    start_run.assert_called_once()


def test_chat_action_blocked_sets_error_ui(client):
    run_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174001")

    with (
        patch(
            "app.chat.router.classify_intent",
            return_value={
                "mode": "ACTION",
                "intent_type": "SWAP",
                "confidence": 0.9,
                "slots": {"token_in": "USDC", "token_out": "WETH", "amount_in": "1"},
                "missing_slots": [],
                "reason": "actionable swap",
            },
        ),
        patch("app.chat.router.create_run_from_action", return_value=run_id),
        patch("app.chat.router.start_run_for_action", return_value={"status": "BLOCKED"}),
    ):
        resp = client.post(
            "/v1/chat/route",
            json={
                "message": "swap 1 usdc to weth",
                "wallet_address": "0x1111111111111111111111111111111111111111",
                "chain_id": 1,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.ACTION.value
    assert "can't proceed" in body["assistant_message"].lower()


def test_chat_action_missing_slots_returns_clarify(client):
    with patch(
        "app.chat.router.classify_intent",
        return_value={
            "mode": "ACTION",
            "intent_type": "SWAP",
            "confidence": 0.7,
            "slots": {"token_in": "USDC", "token_out": "WETH"},
            "missing_slots": ["amount_in"],
            "reason": "amount missing",
        },
    ):
        resp = client.post(
            "/v1/chat/route",
            json={
                "message": "swap usdc to weth",
                "wallet_address": "0x1111111111111111111111111111111111111111",
                "chain_id": 1,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.CLARIFY.value
    assert body["questions"]


def test_chat_action_missing_wallet_returns_clarify(client):
    with patch(
        "app.chat.router.classify_intent",
        return_value={
            "mode": "ACTION",
            "intent_type": "SWAP",
            "confidence": 0.9,
            "slots": {"token_in": "USDC", "token_out": "WETH", "amount_in": "1"},
            "missing_slots": [],
            "reason": "actionable swap",
        },
    ):
        resp = client.post(
            "/v1/chat/route",
            json={"message": "swap 1 usdc to weth", "chain_id": 1},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.CLARIFY.value
    assert body["questions"]
