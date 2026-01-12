from __future__ import annotations

from unittest.mock import patch


def test_chat_route_returns_general_for_smalltalk(client):
    with patch(
        "app.chat.router.classify_intent",
        return_value={
            "mode": "GENERAL",
            "intent_type": "SMALLTALK",
            "confidence": 0.9,
            "slots": {},
            "missing_slots": [],
            "reason": "greeting",
        },
    ):
        resp = client.post("/v1/chat/route", json={"message": "hello"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["mode"] == "GENERAL"
    assert body["assistant_message"]
    assert isinstance(body["suggestions"], list)
    assert len(body["suggestions"]) >= 1
