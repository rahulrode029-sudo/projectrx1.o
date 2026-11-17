"""The assistant must be able to explain how to use RX, in any language."""

from routes import chat as chat_route
from services import voice as voice_service
from services.app_guide import APP_GUIDE, LANGUAGE_RULE


FEATURES = (
    "Chat tab",
    "Voice tab",
    "Messages page",
    "Link WhatsApp page",
    "Theme button",
)


def test_text_prompt_teaches_the_app():
    assert APP_GUIDE in chat_route.SYSTEM_PROMPT

    for feature in FEATURES:
        assert feature in chat_route.SYSTEM_PROMPT


def test_voice_prompt_teaches_the_app():
    for feature in FEATURES:
        assert feature in voice_service.VOICE_SYSTEM_PROMPT


def test_language_rule_covers_any_language():
    assert "any other language" in LANGUAGE_RULE
    assert "same language" in LANGUAGE_RULE


def test_chat_sends_the_guide_to_gemini(client, monkeypatch):
    captured = {}

    def fake_ask(prompt, system=None):
        captured["prompt"] = prompt
        captured["system"] = system
        return "Yeh RX ka upyog karne ka tarika hai."

    monkeypatch.setattr(chat_route.gemini, "ask", fake_ask)

    response = client.post(
        "/chat",
        json={"message": "isme app kaise use karein?"},
    )

    assert response.status_code == 200
    assert response.get_json()["response"].startswith("Yeh RX")
    assert APP_GUIDE in captured["system"]
    assert LANGUAGE_RULE in captured["system"]
    assert captured["prompt"] == "isme app kaise use karein?"
