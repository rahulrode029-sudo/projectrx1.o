"""Web alerts replace the old Telegram delete notifications."""

import pytest

from models import Alert
from services import whatsapp


@pytest.fixture
def alert(session):
    item = Alert(
        kind="deleted",
        title="⚠️ Rahul deleted a message",
        body="the original text",
        seen=False,
    )
    session.add(item)
    session.commit()

    return item.id


def test_store_alert_writes_a_row(session):
    alert_id = whatsapp.store_alert(
        kind="deleted",
        title="⚠️ Rahul deleted a message",
        body="secret text",
    )

    assert alert_id is not None
    assert session.get(Alert, alert_id).body == "secret text"


def test_notify_web_splits_title_from_body(session):
    result = whatsapp.store_alert(
        kind="message",
        title="💬 Rahul",
        body="hello there",
    )

    stored = session.get(Alert, result)

    assert stored.title == "💬 Rahul"
    assert stored.body == "hello there"


def test_messages_page_shows_unread_alerts(client, alert):
    response = client.get("/messages")

    assert response.status_code == 200
    assert b"the original text" in response.data
    assert b"new" in response.data


def test_mark_one_alert_seen(client, alert, session):
    response = client.post(f"/alerts/{alert}/seen")

    assert response.status_code == 302
    assert session.get(Alert, alert).seen is True


def test_mark_all_alerts_seen(client, alert, session):
    assert client.post("/alerts/seen-all").status_code == 302
    assert session.get(Alert, alert).seen is True


def test_unknown_alert_returns_404(client):
    assert client.post("/alerts/999999/seen").status_code == 404
