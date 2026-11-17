"""Tests for Gemini model fallback.

The default flash model regularly returns 503 under load. A single
overloaded model must not turn into "Failed to generate response" for
the user, so these tests pin down the fallback behaviour.
"""

import dataclasses
import types

import pytest

from services import gemini


class _FakeModels:
    def __init__(self, failures):
        self.failures = failures
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)

        if model in self.failures:
            raise RuntimeError(self.failures[model])

        return types.SimpleNamespace(text="hello from " + model)


def _patch(monkeypatch, failures):
    """Wire up a fake Gemini client with a controlled model list."""

    models = _FakeModels(failures)
    client = types.SimpleNamespace(models=models)

    monkeypatch.setattr(gemini, "get_client", lambda: client)
    monkeypatch.setattr(gemini, "_working_model", None)
    monkeypatch.setattr(
        gemini,
        "settings",
        dataclasses.replace(
            gemini.settings,
            gemini_chat_model="gemini-primary",
            gemini_fallback_models=("gemini-primary", "gemini-backup"),
        ),
    )

    return models


def test_ask_falls_back_when_the_model_is_overloaded(monkeypatch):
    models = _patch(
        monkeypatch,
        {"gemini-primary": "503 UNAVAILABLE. high demand"},
    )

    assert gemini.ask("hii") == "hello from gemini-backup"
    assert models.calls == ["gemini-primary", "gemini-backup"]
    assert gemini._working_model == "gemini-backup"


def test_ask_remembers_the_working_model(monkeypatch):
    models = _patch(
        monkeypatch,
        {"gemini-primary": "429 RESOURCE_EXHAUSTED"},
    )

    gemini.ask("one")
    gemini.ask("two")

    # The failing model is tried only on the first request.
    assert models.calls == [
        "gemini-primary",
        "gemini-backup",
        "gemini-backup",
    ]


def test_ask_does_not_retry_a_permanent_error(monkeypatch):
    models = _patch(
        monkeypatch,
        {"gemini-primary": "400 API_KEY_INVALID"},
    )

    with pytest.raises(RuntimeError):
        gemini.ask("hii")

    assert models.calls == ["gemini-primary"]
