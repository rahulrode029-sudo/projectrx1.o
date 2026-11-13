"""Tests for storing, finding and flagging messages."""

from datetime import datetime, timezone

from services import memory

JID = "919999999999@s.whatsapp.net"


def test_store_message_creates_contact_and_conversation(session):
    message = memory.store_message(
        session,
        chat_jid=JID,
        wa_message_id="MSG-1",
        body="hello there",
        sender_jid=JID,
        sender_name="Tester",
        sender_phone="919999999999",
    )

    assert message.id is not None
    assert message.contact is not None
    assert message.contact.label == "Tester"
    assert message.conversation is not None


def test_storing_the_same_message_twice_is_idempotent(session):
    first = memory.store_message(
        session, chat_jid=JID, wa_message_id="MSG-DUP", body="once"
    )
    second = memory.store_message(
        session, chat_jid=JID, wa_message_id="MSG-DUP", body="once"
    )

    assert first.id == second.id


def test_mark_deleted_keeps_the_content(session):
    memory.store_message(
        session,
        chat_jid=JID,
        wa_message_id="MSG-DEL",
        body="the 5pm meeting is cancelled",
        sender_jid=JID,
        sender_name="Tester",
    )

    flagged = memory.mark_deleted(session, "MSG-DEL", "revoke")

    assert flagged is not None
    assert flagged.is_deleted is True
    assert flagged.deleted_at is not None
    assert flagged.delete_type == "revoke"

    # The whole point: the content survives the deletion.
    assert flagged.body == "the 5pm meeting is cancelled"


def test_mark_deleted_for_an_unknown_message_returns_none(session):
    assert memory.mark_deleted(session, "NOT-A-MESSAGE") is None


def test_marking_twice_keeps_the_first_timestamp(session):
    memory.store_message(
        session, chat_jid=JID, wa_message_id="MSG-TWICE", body="text"
    )

    first = memory.mark_deleted(session, "MSG-TWICE")
    first_deleted_at = first.deleted_at

    second = memory.mark_deleted(session, "MSG-TWICE")

    assert second.deleted_at == first_deleted_at


def test_resolve_contact_by_name(session):
    memory.store_message(
        session,
        chat_jid=JID,
        wa_message_id="MSG-NAME",
        body="text",
        sender_jid=JID,
        sender_name="Rahul Sharma",
        sender_phone="919999999999",
    )

    assert memory.resolve_contact(session, "Rahul Sharma").label == (
        "Rahul Sharma"
    )


def test_resolve_contact_by_partial_name(session):
    memory.store_message(
        session,
        chat_jid=JID,
        wa_message_id="MSG-PART",
        body="text",
        sender_jid=JID,
        sender_name="Priya",
    )

    assert memory.resolve_contact(session, "Pri") is not None


def test_resolve_contact_by_phone_digits(session):
    memory.store_message(
        session,
        chat_jid=JID,
        wa_message_id="MSG-PHONE",
        body="text",
        sender_jid=JID,
        sender_name="Rahul",
        sender_phone="919999999999",
    )

    assert memory.resolve_contact(session, "9999999999") is not None


def test_resolve_contact_for_an_unknown_name(session):
    assert memory.resolve_contact(session, "Nobody At All") is None


def test_recent_from_returns_oldest_first(session):
    now = datetime.now(timezone.utc)

    for index in range(3):
        memory.store_message(
            session,
            chat_jid=JID,
            wa_message_id=f"MSG-REC-{index}",
            body=f"message {index}",
            sender_jid=JID,
            sender_name="Tester",
            sent_at=now,
        )

    contact = memory.resolve_contact(session, "Tester")

    messages = memory.recent_from(session, contact, limit=3)

    assert [m.body for m in messages] == [
        "message 0",
        "message 1",
        "message 2",
    ]


def test_list_deleted_finds_flagged_messages(session):
    memory.store_message(
        session, chat_jid=JID, wa_message_id="MSG-LIST", body="bye"
    )
    memory.mark_deleted(session, "MSG-LIST")

    deleted = memory.list_deleted(session)

    assert any(m.wa_message_id == "MSG-LIST" for m in deleted)


def test_notify_mode_defaults_to_summary(session):
    memory.store_message(
        session,
        chat_jid=JID,
        wa_message_id="MSG-MODE",
        body="text",
        sender_jid=JID,
        sender_name="Modetest",
    )

    contact = memory.resolve_contact(session, "Modetest")

    assert memory.get_preference(session, contact).notify_mode == "summary"


def test_set_notify_mode_accepts_known_modes(session):
    memory.store_message(
        session,
        chat_jid=JID,
        wa_message_id="MSG-MODE2",
        body="text",
        sender_jid=JID,
        sender_name="Modetest2",
    )

    contact = memory.resolve_contact(session, "Modetest2")

    assert memory.set_notify_mode(session, contact, "silent") is True
    assert memory.get_preference(session, contact).notify_mode == "silent"


def test_set_notify_mode_rejects_unknown_modes(session):
    memory.store_message(
        session,
        chat_jid=JID,
        wa_message_id="MSG-MODE3",
        body="text",
        sender_jid=JID,
        sender_name="Modetest3",
    )

    contact = memory.resolve_contact(session, "Modetest3")

    assert memory.set_notify_mode(session, contact, "nonsense") is False
    assert memory.get_preference(session, contact).notify_mode == "summary"
