"""Multiple accounts, isolation and phone-based password recovery."""

import uuid

from sqlalchemy import select
from urllib.parse import urlparse, parse_qs

from config import settings
from models import Alert, Contact, Message, WebUser
from services import accounts, memory, recovery
from services.tenancy import owner_scope


def test_admin_can_create_account_and_it_can_log_in(admin_client, anon_client):
    response = admin_client.post(
        "/admin/users/create",
        data={
            "username": "newperson",
            "display_name": "New Person",
            "phone": "9123456789",
            "password": "a-good-password",
        },
    )

    assert response.status_code == 302

    login = anon_client.post(
        "/login", data={"username": "newperson", "password": "a-good-password"}
    )

    assert login.status_code == 302
    assert anon_client.get("/").status_code == 200


def test_regular_user_cannot_open_admin_pages(other_client):
    client, _ = other_client

    assert client.get("/admin/users").status_code == 403
    assert client.post("/admin/users/create", data={}).status_code == 403


def test_user_cannot_see_or_delete_another_users_contact(client, other_client, session):
    other, _ = other_client

    with owner_scope(accounts.bootstrap_admin_id()):
        contact = memory.get_or_create_contact(
            session, "919999888877@s.whatsapp.net", "PrivateContact"
        )
        session.commit()

    contact_id = contact.id

    page = other.get("/messages").get_data(as_text=True)

    assert "PrivateContact" not in page

    response = other.post(f"/contacts/{contact_id}/delete", follow_redirects=True)

    assert response.status_code == 200
    assert session.get(Contact, contact_id) is not None


def test_admin_cannot_see_another_users_alerts(client, other_client, session):
    _, user = other_client

    with owner_scope(user.id):
        session.add(
            Alert(
                owner_id=user.id,
                kind="message",
                title="Private alert",
                body="secret body",
            )
        )
        session.commit()

    page = client.get("/messages").get_data(as_text=True)

    assert "Private alert" not in page
    assert "secret body" not in page


def test_two_users_can_have_the_same_contact_jid(other_client, session):
    _, user = other_client
    jid = "918888777766@s.whatsapp.net"

    with owner_scope(accounts.bootstrap_admin_id()):
        first = memory.get_or_create_contact(session, jid, "AdminCopy")
        session.commit()

    with owner_scope(user.id):
        second = memory.get_or_create_contact(session, jid, "UserCopy")
        session.commit()

    assert first.id != second.id
    assert first.owner_id != second.owner_id


def test_sidecar_token_routes_events_to_the_right_user(other_client, session):
    client, user = other_client

    response = client.post(
        "/wa/events",
        json={
            "type": "contact",
            "jid": "917755664433@s.whatsapp.net",
            "push_name": "TokenContact",
        },
        headers={
            "X-WA-Secret": settings.wa_shared_secret,
            "X-RX-Token": user.wa_token,
        },
    )

    assert response.status_code == 200

    contact = session.scalar(
        select(Contact).where(Contact.jid == "917755664433@s.whatsapp.net")
    )

    assert contact is not None
    assert contact.owner_id == user.id


def test_sidecar_message_api_is_owner_scoped(client, other_client, session):
    other, user = other_client
    marker = "PRIVATE-ADMIN-MESSAGE-" + uuid.uuid4().hex[:8]

    with owner_scope(accounts.bootstrap_admin_id()):
        memory.store_message(
            session,
            chat_jid="916644553322@s.whatsapp.net",
            wa_message_id=marker,
            body=marker,
            sender_jid="916644553322@s.whatsapp.net",
            sender_name="ScopeCheck",
        )
        session.commit()

    headers = {
        "X-WA-Secret": settings.wa_shared_secret,
        "X-RX-Token": user.wa_token,
    }

    payload = other.get("/wa/messages", headers=headers).get_json()

    assert marker not in [row["body"] for row in payload["messages"]]

    own = client.get(
        "/wa/messages", headers={"X-WA-Secret": settings.wa_shared_secret}
    ).get_json()

    assert marker in [row["body"] for row in own["messages"]]


def test_forgot_password_flow_sets_a_new_password(other_client, anon_client, monkeypatch):
    client, user = other_client
    captured = {}

    def fake_send_otp(account, code):
        captured["code"] = code
        return "whatsapp"

    def fake_send_link(account, link):
        captured["link"] = link
        return "whatsapp"

    monkeypatch.setattr(recovery, "send_otp", fake_send_otp)
    monkeypatch.setattr(recovery, "send_reset_link", fake_send_link)

    assert client.get("/forgot-password").status_code == 200

    sent = client.post(
        "/forgot-password/send", data={"phone": user.phone}, follow_redirects=True
    )

    assert sent.status_code == 200
    assert "code sent" in sent.get_data(as_text=True).lower()

    verified = client.post(
        "/forgot-password/verify",
        data={"code": captured["code"]},
        follow_redirects=True,
    )

    assert verified.status_code == 200
    assert "reset link sent" in verified.get_data(as_text=True).lower()

    token = parse_qs(urlparse(captured["link"]).query)["token"][0]

    assert anon_client.get(f"/reset-password?token={token}").status_code == 200

    result = anon_client.post(
        "/reset-password",
        data={
            "token": token,
            "password": "brand-new-password",
            "confirm_password": "brand-new-password",
        },
    )

    assert result.status_code == 302

    login = anon_client.post(
        "/login",
        data={"username": user.username, "password": "brand-new-password"},
    )

    assert login.status_code == 302


def test_reset_link_cannot_be_used_twice(other_client, monkeypatch):
    _, user = other_client
    link = recovery.create_reset_link(user)
    token = parse_qs(urlparse(link).query)["token"][0]

    assert recovery.reset_user_for_token(token).id == user.id

    assert accounts.set_password(user.id, "another-password-123")

    recovery.consume_token_for_user(user.id)

    assert recovery.reset_user_for_token(token) is None


def test_changing_password_ends_old_sessions(client):
    client.post(
        "/account/password",
        data={
            "old_password": "test-password",
            "new_password": "fresh-password-123",
            "confirm_password": "fresh-password-123",
        },
    )

    assert client.get("/messages").status_code == 200

    # Leave the shared admin password as the other tests expect it.
    accounts.set_password(accounts.bootstrap_admin_id(), "test-password")
