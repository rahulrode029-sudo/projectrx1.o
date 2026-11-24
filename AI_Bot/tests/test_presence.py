"""WhatsApp active-session tracking for selected contacts."""

from datetime import datetime, timezone

from sqlalchemy import select

from models import Alert, Contact, ContactPreference, PresenceSession
from services import memory, presence


def _epoch(hour: int, minute: int) -> int:
    return int(
        datetime(2026, 11, 25, hour, minute, tzinfo=timezone.utc).timestamp()
    )


def _tracked_contact(session, jid: str, label: str, enabled: bool = True):
    contact = memory.get_or_create_contact(session, jid, label)
    preference = memory.get_preference(session, contact)
    preference.track_sessions = enabled
    session.commit()
    return contact


def test_tracking_toggle_is_saved(client, session):
    contact = memory.get_or_create_contact(
        session, "919111110001@s.whatsapp.net", "Toggle Me"
    )
    session.commit()

    response = client.post(
        f"/contacts/{contact.id}/tracking",
        data={"enabled": "1", "next": "/messages?contact=Toggle+Me"},
    )

    assert response.status_code == 302
    assert memory.get_preference(session, contact).track_sessions is True

    client.post(
        f"/contacts/{contact.id}/tracking",
        data={"enabled": "0"},
    )

    assert memory.get_preference(session, contact).track_sessions is False


def test_tracked_endpoint_lists_only_opted_in_contacts(client, auth_headers, session):
    on_jid = "919111110002@s.whatsapp.net"
    off_jid = "919111110003@s.whatsapp.net"

    _tracked_contact(session, on_jid, "Tracked One", True)
    _tracked_contact(session, off_jid, "Not Tracked", False)

    response = client.get("/wa/tracked", headers=auth_headers)

    assert response.status_code == 200
    assert on_jid in response.get_json()["jids"]
    assert off_jid not in response.get_json()["jids"]


def test_presence_event_stores_a_session_and_an_alert(client, auth_headers, session):
    jid = "919111110004@s.whatsapp.net"
    _tracked_contact(session, jid, "Amit")

    response = client.post(
        "/wa/events",
        json={
            "type": "presence_session",
            "jid": jid,
            "start_epoch": _epoch(5, 40),   # 11:10 IST
            "end_epoch": _epoch(5, 55),     # 11:25 IST
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["recorded"] is True

    row = session.scalar(
        select(PresenceSession).where(PresenceSession.contact_id.in_(
            select(Contact.id).where(Contact.jid == jid)
        ))
    )

    assert row is not None
    assert row.duration_seconds == 15 * 60

    alert = session.scalar(
        select(Alert).where(
            Alert.kind == "online_session", Alert.contact_id == row.contact_id
        )
    )

    assert alert is not None
    assert "25 Nov 11:10 → 25 Nov 11:25" in alert.body
    assert "15 min" in alert.body


def test_presence_event_is_ignored_for_untracked_contacts(client, auth_headers, session):
    jid = "919111110005@s.whatsapp.net"
    _tracked_contact(session, jid, "Skipped", False)

    before = len(session.scalars(select(PresenceSession)).all())

    response = client.post(
        "/wa/events",
        json={
            "type": "presence_session",
            "jid": jid,
            "start_epoch": _epoch(6, 0),
            "end_epoch": _epoch(6, 20),
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.get_json()["recorded"] is False
    assert len(session.scalars(select(PresenceSession)).all()) == before


def test_close_sessions_merge_into_one_window(client, auth_headers, session):
    jid = "919111110006@s.whatsapp.net"
    _tracked_contact(session, jid, "Flappy")

    client.post(
        "/wa/events",
        json={
            "type": "presence_session",
            "jid": jid,
            "start_epoch": _epoch(7, 0),
            "end_epoch": _epoch(7, 10),
        },
        headers=auth_headers,
    )

    client.post(
        "/wa/events",
        json={
            "type": "presence_session",
            "jid": jid,
            "start_epoch": _epoch(7, 11),
            "end_epoch": _epoch(7, 30),
        },
        headers=auth_headers,
    )

    rows = session.scalars(
        select(PresenceSession).where(PresenceSession.contact_id.in_(
            select(Contact.id).where(Contact.jid == jid)
        ))
    ).all()

    assert len(rows) == 1
    assert rows[0].duration_seconds == 30 * 60


def test_messages_page_and_live_snapshot_show_sessions(client, auth_headers, session):
    jid = "919111110007@s.whatsapp.net"
    _tracked_contact(session, jid, "Live Contact")

    client.post(
        "/wa/events",
        json={
            "type": "presence_session",
            "jid": jid,
            "start_epoch": _epoch(8, 0),
            "end_epoch": _epoch(8, 45),
        },
        headers=auth_headers,
    )

    page = client.get("/messages")

    assert page.status_code == 200
    # 08:00/08:45 UTC → 13:30/14:15 IST.
    assert b"25 Nov 13:30 \xe2\x86\x92 25 Nov 14:15" in page.data

    chat = client.get("/")

    assert chat.status_code == 200
    assert b"25 Nov 13:30 \xe2\x86\x92 25 Nov 14:15" in chat.data

    live = client.get("/messages/live").get_json()

    assert any(
        item["contact"] == "Live Contact" and item["minutes"] == 45
        for item in live["sessions"]
    )


def test_no_sessions_shows_a_hint(other_client):
    other = other_client[0]

    messages = other.get("/messages")
    chat = other.get("/")

    assert messages.status_code == 200
    assert b"No sessions recorded yet" in messages.data
    assert chat.status_code == 200
    assert b"No sessions recorded yet" in chat.data


def test_another_owner_cannot_see_the_sessions(client, other_client, auth_headers, session):
    jid = "919111110008@s.whatsapp.net"
    _tracked_contact(session, jid, "Private Contact")

    client.post(
        "/wa/events",
        json={
            "type": "presence_session",
            "jid": jid,
            "start_epoch": _epoch(9, 0),
            "end_epoch": _epoch(9, 15),
        },
        headers=auth_headers,
    )

    other_page = other_client[0].get("/messages/live").get_json()

    assert other_page["sessions"] == []


def test_deleting_a_contact_removes_its_sessions(client, auth_headers, session):
    jid = "919111110009@s.whatsapp.net"
    contact = _tracked_contact(session, jid, "Remove Me")

    client.post(
        "/wa/events",
        json={
            "type": "presence_session",
            "jid": jid,
            "start_epoch": _epoch(10, 0),
            "end_epoch": _epoch(10, 20),
        },
        headers=auth_headers,
    )

    assert session.scalars(
        select(PresenceSession).where(PresenceSession.contact_id == contact.id)
    ).all()

    client.post(f"/contacts/{contact.id}/delete")

    assert session.scalars(
        select(PresenceSession).where(PresenceSession.contact_id == contact.id)
    ).all() == []
