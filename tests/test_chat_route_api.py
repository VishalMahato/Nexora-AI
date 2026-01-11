from __future__ import annotations


def test_chat_route_returns_clarify(client):
    resp = client.post("/v1/chat/route", json={"message": "hello"})
    assert resp.status_code == 200

    body = resp.json()
    assert body["mode"] == "CLARIFY"
    assert body["assistant_message"]
    assert isinstance(body["questions"], list)
    assert len(body["questions"]) >= 1
