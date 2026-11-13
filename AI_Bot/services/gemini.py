"""Shared Gemini access.

Every Gemini call in the project goes through this module so the
API key handling, the model choice and the error behaviour are
defined in exactly one place.
"""

import google.genai as genai

from config import settings


_client = None

# Flipped to False the first time a search-grounded call is rejected,
# so we stop paying for a doomed request on every call.
_search_available = True


def get_client():
    """Return the shared Gemini client, building it on first use.

    Lazy construction means a missing API key surfaces as a clear
    error at request time instead of an import-time crash.
    """

    global _client

    if _client is None:

        if not settings.has_gemini:
            raise RuntimeError(
                "Gemini_API_KEY is not set. Add it to .env and restart."
            )

        _client = genai.Client(api_key=settings.gemini_api_key)

    return _client


def ask(prompt, system=None):
    """Plain text generation.

    Use for questions that do not need current information.
    """

    config = {"system_instruction": system} if system else None

    response = get_client().models.generate_content(
        model=settings.gemini_chat_model,
        contents=prompt,
        config=config,
    )

    return response.text


def ask_with_search(prompt, system=None):
    """Text generation grounded in Google Search results.

    Google Search grounding is not included on the free tier, so this
    falls back to plain generation when the tool is unavailable. The
    fallback is remembered, so the failing request is only made once
    per process instead of on every call.

    Movie features do not depend on this: TMDB already provides
    authoritative structured data, which is handed to `ask` instead.
    """

    global _search_available

    if _search_available:

        config = {"tools": [{"google_search": {}}]}

        if system:
            config["system_instruction"] = system

        try:

            response = get_client().models.generate_content(
                model=settings.gemini_chat_model,
                contents=prompt,
                config=config,
            )

            return response.text

        except Exception as error:

            if "RESOURCE_EXHAUSTED" not in str(error) and "429" not in str(error):
                raise

            print(
                "Google Search grounding is unavailable on this API key "
                "(free tier). Falling back to plain generation. Enable "
                "billing to switch this back on."
            )

            _search_available = False

    return ask(prompt, system)


def summarize(text, max_words=30):
    """Reduce a message to a single short sentence.

    Used to tell the owner what a message was about without
    showing them the raw text.
    """

    prompt = (
        "Summarise the message below in one short sentence of at most "
        f"{max_words} words. State who it is about and what they want. "
        "Reply with the summary only: no preamble, no quotes, no label.\n\n"
        f"{text}"
    )

    try:
        return ask(prompt).strip().strip('"')
    except Exception as error:
        print(f"Summarisation failed: {error}")
        return ""


def embed(texts):
    """Embed one or many strings for semantic search.

    Returns a list of float vectors.
    """

    if isinstance(texts, str):
        texts = [texts]

    if not texts:
        return []

    response = get_client().models.embed_content(
        model="gemini-embedding-001",
        contents=texts,
    )

    return [item.values for item in response.embeddings]


def chat(system, message):
    """One-shot chat turn that returns the reply text.

    `system` is the persona / instruction block.
    """

    return ask(message, system=system)
