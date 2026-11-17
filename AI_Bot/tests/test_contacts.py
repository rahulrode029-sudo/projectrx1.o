"""Adding and removing contacts from the Messages page."""

from sqlalchemy import select

from models import Alert, Contact, ContactPreference, Conversation, Message
from services import memory


def _contact_count(session):
    return len(session.scalars(select(Contact)).all())


def test_add_contact_from_phone(client, session):
    before = _contact_count(session)

    response = client.post(
        "/contacts/add",
        data={"name": "Rahul", "phone": "919999999999", "jid": ""},
    )

    assert response.status_code == 302

    contact = session.scalar(
        select(Contact).where(Contact.jid == "919999999999@s.whatsapp.net")
    )

    assert contact is not None
    assert contact.push_name == "Rahul"
    assert _contact_count(session) == before + 1
    assert session.scalar(
        select(ContactPreference).where(ContactPreference.contact_id == contact.id)
    ) is not None


def test_add_contact_from_jid(client, session):
    before = _contact_count(session)

    response = client.post(
        "/contacts/add",
        data={"name": "Test", "phone": "", "jid": "123@s.whatsapp.net"},
    )

    assert response.status_code == 302
    assert session.scalar(
        select(Contact).where(Contact.jid == "123@s.whatsapp.net")
    ) is not None
    assert _contact_count(session) == before + 1


def test_add_contact_without_number_is_rejected(client, session):
    before = _contact_count(session)

    response = client.post(
        "/contacts/add",
        data={"name": "Nobody", "phone": "", "jid": ""},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Enter a phone number" in response.data
    assert _contact_count(session) == before


def test_duplicate_contact_is_rejected(client, session):
    before = _contact_count(session)

    client.post("/contacts/add", data={"name": "First", "phone": "911111111111"})

    response = client.post(
        "/contacts/add",
        data={"name": "Second", "phone": "911111111111"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"already in the list" in response.data
    assert _contact_count(session) == before + 1


def test_delete_contact_removes_its_data(client, session):
    jid = "918888888888@s.whatsapp.net"

    message = memory.store_message(
        session,
        chat_jid=jid,
        wa_message_id="DELETE-CONTACT-1",
        body="stored text",
        sender_jid=jid,
        sender_name="DeleteMe",
    )
    contact_id = message.contact_id
    conversation_id = message.conversation_id

    session.add(
        Alert(kind="deleted", title="alert", body="body", contact_id=contact_id)
    )
    session.commit()

    response = client.post(f"/contacts/{contact_id}/delete")

    assert response.status_code == 302
    assert session.get(Contact, contact_id) is None
    assert session.scalars(
        select(Message).where(Message.contact_id == contact_id)
    ).all() == []
    assert session.scalars(
        select(Alert).where(Alert.contact_id == contact_id)
    ).all() == []
    assert session.get(Conversation, conversation_id).contact_id is None


def test_messages_page_offers_add_and_delete(client, session):
    contact = memory.get_or_create_contact(session, "917777777777@s.whatsapp.net", "Visible")
    session.commit()

    response = client.get("/messages")

    assert response.status_code == 200
    assert b'action="/contacts/add"' in response.data
    assert f"/contacts/{contact.id}/delete".encode() in response.data
