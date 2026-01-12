from __future__ import annotations

import uuid
from unittest.mock import patch

from app.chat.contracts import IntentMode
from app.chat.state_store import set as set_state
from app.chat.state_store import get as get_state


def test_chat_clarify_loop_amount_followup(client):
    run_id = uuid.UUID("123e4567-e89b-12d3-a456-426614174010")

    with (
        patch(
            "app.chat.router.classify_intent",
            return_value={
                "mode": "CLARIFY",
                "intent_type": "SWAP",
                "confidence": 0.7,
                "slots": {"token_in": "USDC", "token_out": "WETH"},
                "missing_slots": ["amount_in"],
                "reason": "amount missing",
            },
        ),
        patch("app.chat.router.create_run_from_action", return_value=run_id),
        patch("app.chat.router.start_run_for_action", return_value={"status": "AWAITING_APPROVAL"}),
    ):
        first = client.post(
            "/v1/chat/route",
            json={
                "conversation_id": "c1",
                "message": "swap usdc to weth",
                "wallet_address": "0x1111111111111111111111111111111111111111",
                "chain_id": 1,
            },
        )

        assert first.status_code == 200
        first_body = first.json()
        assert first_body["mode"] == IntentMode.CLARIFY.value
        assert first_body["pending"] is True

        second = client.post(
            "/v1/chat/route",
            json={"conversation_id": "c1", "message": "1"},
        )

    assert second.status_code == 200
    second_body = second.json()
    assert second_body["mode"] == IntentMode.ACTION.value
    assert second_body["run_id"] == str(run_id)


def test_chat_clarify_loop_wrong_conversation_id(client):
    with patch(
        "app.chat.router.classify_intent",
        return_value={
            "mode": "CLARIFY",
            "intent_type": "SWAP",
            "confidence": 0.7,
            "slots": {"token_in": "USDC", "token_out": "WETH"},
            "missing_slots": ["amount_in"],
            "reason": "amount missing",
        },
    ):
        client.post(
            "/v1/chat/route",
            json={
                "conversation_id": "c1",
                "message": "swap usdc to weth",
                "wallet_address": "0x1111111111111111111111111111111111111111",
                "chain_id": 1,
            },
        )

        resp = client.post("/v1/chat/route", json={"conversation_id": "c2", "message": "1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.CLARIFY.value


def test_chat_clarify_loop_missing_wallet(client):
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
            json={"conversation_id": "c3", "message": "swap 1 usdc to weth", "chain_id": 1},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.CLARIFY.value
    assert body["pending"] is True


def test_chat_state_store_ttl_expiry():
    set_state(
        "c-expired",
        {
            "intent_type": "SWAP",
            "partial_slots": {"token_in": "USDC"},
            "missing_slots": ["amount_in"],
            "wallet_address": None,
            "chain_id": None,
        },
        ttl_seconds=-1,
    )

    assert get_state("c-expired") is None
