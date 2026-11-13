"""Tests for the HTTP surface."""

MESSAGE_EVENT = {
    "type": "message",
    "chat_jid": "918888888888@s.whatsapp.net",
    "wa_message_id": "API-MSG-1",
    "body": "are you free this evening?",
    "from_me": False,
    "sender_jid": "918888888888@s.whatsapp.net",
    "sender_name": "ApiTester",
}


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_index_page_loads(client):
    assert client.get("/").status_code == 200


def test_messages_page_loads(client):
    assert client.get("/messages").status_code == 200


def test_chat_rejects_an_empty_message(client):
    response = client.post("/chat", json={"message": "   "})

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_chat_rejects_a_missing_body(client):
    response = client.post("/chat", json={})

    assert response.status_code == 400


def test_events_are_refused_without_the_secret(client):
    response = client.post("/wa/events", json=MESSAGE_EVENT)

    assert response.status_code == 401


def test_events_are_refused_with_the_wrong_secret(client):
    response = client.post(
        "/wa/events",
        json=MESSAGE_EVENT,
        headers={"X-WA-Secret": "wrong"},
    )

    assert response.status_code == 401


def test_a_message_event_is_stored(client, auth_headers):
    response = client.post("/wa/events", json=MESSAGE_EVENT, headers=auth_headers)

    assert response.status_code == 200

    body = response.get_json()

    assert body["ok"] is True
    assert body["contact"] == "ApiTester"


def test_a_revoke_event_flags_the_stored_message(client, auth_headers):
    client.post("/wa/events", json=MESSAGE_EVENT, headers=auth_headers)

    revoke = {
        "type": "revoke",
        "key": {"id": "API-MSG-1", "remoteJid": MESSAGE_EVENT["chat_jid"]},
    }

    response = client.post("/wa/events", json=revoke, headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    listing = client.get("/wa/messages", headers=auth_headers).get_json()

    stored = [m for m in listing["messages"] if m["wa_message_id"] == "API-MSG-1"]

    assert stored, "the message should still be in the archive"

    assert stored[0]["is_deleted"] is True

    # The content is what makes the feature useful.
    assert stored[0]["body"] == "are you free this evening?"


def test_an_unknown_event_type_is_rejected(client, auth_headers):
    response = client.post(
        "/wa/events", json={"type": "nonsense"}, headers=auth_headers
    )

    assert response.status_code == 400


def test_contacts_endpoint_lists_known_contacts(client, auth_headers):
    client.post("/wa/events", json=MESSAGE_EVENT, headers=auth_headers)

    response = client.get("/wa/contacts", headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json()["count"] >= 1


def test_mode_endpoint_changes_the_notify_mode(client, auth_headers):
    client.post("/wa/events", json=MESSAGE_EVENT, headers=auth_headers)

    response = client.post(
        "/wa/mode",
        json={"contact": "ApiTester", "mode": "silent"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["mode"] == "silent"


def test_mode_endpoint_rejects_an_unknown_mode(client, auth_headers):
    client.post("/wa/events", json=MESSAGE_EVENT, headers=auth_headers)

    response = client.post(
        "/wa/mode",
        json={"contact": "ApiTester", "mode": "wrong"},
        headers=auth_headers,
    )

    assert response.status_code == 400
