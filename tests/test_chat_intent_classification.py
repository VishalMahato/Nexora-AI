from __future__ import annotations

from unittest.mock import patch

from app.chat.contracts import IntentMode


def test_chat_query_mode(client):
    with patch(
        "app.chat.router.classify_intent",
        return_value={
            "mode": "QUERY",
            "intent_type": "BALANCE",
            "confidence": 0.9,
            "slots": {},
            "missing_slots": [],
            "reason": "wallet query",
        },
    ):
        resp = client.post(
            "/v1/chat/route",
            json={
                "message": "what's my balance?",
                "wallet_address": "0x1111111111111111111111111111111111111111",
                "chain_id": 1,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.QUERY.value
    assert body["classification"]["intent_type"] == "BALANCE"
    assert body["questions"] == []


def test_chat_action_mode(client):
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
        resp = client.post("/v1/chat/route", json={"message": "swap 1 usdc to weth"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.ACTION.value
    assert body["questions"] == []


def test_chat_clarify_mode(client):
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
        resp = client.post("/v1/chat/route", json={"message": "swap usdc to weth"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.CLARIFY.value
    assert body["questions"]


def test_chat_invalid_classification_fallback(client):
    with patch("app.chat.router.classify_intent", return_value={"bad": "data"}):
        resp = client.post("/v1/chat/route", json={"message": "swap usdc to weth"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.CLARIFY.value
    assert body["questions"]
