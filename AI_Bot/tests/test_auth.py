"""Password protection for the web UI."""

import pytest

from config import settings


PAGES = ("/", "/messages", "/movies", "/movie?q=Nosferatu", "/qr", "/qr.svg")


@pytest.mark.parametrize("path", PAGES)
def test_pages_require_login(anon_client, path):
    response = anon_client.get(path)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_chat_requires_login(anon_client):
    response = anon_client.post("/chat", json={"message": "hello"})

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_health_stays_public(anon_client):
    assert anon_client.get("/health").status_code == 200


def test_login_page_is_public(anon_client):
    assert anon_client.get("/login").status_code == 200


def test_wrong_password_is_rejected(anon_client):
    response = anon_client.post("/login", data={"password": "not-the-password"})

    assert response.status_code == 401
    assert b"Wrong password" in response.data


def test_correct_password_logs_in(anon_client):
    response = anon_client.post("/login", data={"password": settings.web_password})

    assert response.status_code == 302
    assert anon_client.get("/messages").status_code == 200


def test_logout_ends_the_session(client):
    assert client.get("/logout").status_code == 302
    assert client.get("/messages").status_code == 302


def test_login_does_not_redirect_offsite(anon_client):
    response = anon_client.post(
        "/login",
        data={"password": settings.web_password, "next": "//evil.example"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_wa_api_still_uses_shared_secret(anon_client):
    """The sidecar is not a browser, so it must not need a session."""

    response = anon_client.get("/wa/messages", headers={"X-WA-Secret": settings.wa_shared_secret})

    assert response.status_code == 200
