from __future__ import annotations

from unittest.mock import patch

from app.chat.contracts import IntentMode


def test_chat_query_balance(client):
    with (
        patch(
            "app.chat.router.classify_intent",
            return_value={
                "mode": "QUERY",
                "intent_type": "BALANCE",
                "confidence": 0.9,
                "slots": {"token_symbol": "USDC"},
                "missing_slots": [],
                "reason": "token balance",
            },
        ),
        patch(
            "app.chat.router.get_token_balance",
            return_value={"symbol": "USDC", "balance": "123.45", "decimals": 6, "token": "0x1"},
        ),
    ):
        resp = client.post(
            "/v1/chat/route",
            json={
                "message": "what is my usdc balance?",
                "wallet_address": "0x1111111111111111111111111111111111111111",
                "chain_id": 1,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.QUERY.value
    assert "USDC" in body["assistant_message"]
    assert body["data"]["balance"]["balance"] == "123.45"


def test_chat_query_snapshot(client):
    with (
        patch(
            "app.chat.router.classify_intent",
            return_value={
                "mode": "QUERY",
                "intent_type": "SNAPSHOT",
                "confidence": 0.8,
                "slots": {},
                "missing_slots": [],
                "reason": "snapshot query",
            },
        ),
        patch(
            "app.chat.router.get_wallet_snapshot",
            return_value={"native": {"balanceWei": "1"}, "erc20": [], "allowances": []},
        ),
    ):
        resp = client.post(
            "/v1/chat/route",
            json={
                "message": "show my wallet",
                "wallet_address": "0x1111111111111111111111111111111111111111",
                "chain_id": 1,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.QUERY.value
    assert "snapshot" in body["data"]


def test_chat_query_missing_wallet_or_chain(client):
    with patch(
        "app.chat.router.classify_intent",
        return_value={
            "mode": "QUERY",
            "intent_type": "BALANCE",
            "confidence": 0.9,
            "slots": {"token_symbol": "USDC"},
            "missing_slots": [],
            "reason": "token balance",
        },
    ):
        resp = client.post("/v1/chat/route", json={"message": "what is my usdc balance?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.CLARIFY.value
    assert body["questions"]


def test_chat_query_allowlists(client):
    with (
        patch(
            "app.chat.router.classify_intent",
            return_value={
                "mode": "QUERY",
                "intent_type": "ALLOWLISTS",
                "confidence": 0.8,
                "slots": {},
                "missing_slots": [],
                "reason": "allowlists",
            },
        ),
        patch(
            "app.chat.router.get_allowlists",
            return_value={"tokens": {}, "routers": {}},
        ),
    ):
        resp = client.post(
            "/v1/chat/route",
            json={"message": "what are the supported tokens?"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == IntentMode.QUERY.value
    assert "allowlists" in body["data"]
