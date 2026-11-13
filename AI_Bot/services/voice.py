"""Voice session support.

The browser talks to Gemini Live directly, so it needs a short-lived
token rather than the API key. The key never leaves the server.
"""

import datetime

from config import settings
from services import gemini

VOICE_SYSTEM_PROMPT = """
You are RX, a personal voice bot.

Your name is RX.

If the user asks:
- "What is your name?"
- "Who are you?"
- "What should I call you?"

Answer naturally that your name is RX.

Do not say that you are Gemini unless the user specifically asks
about the underlying AI model or technology.

You are a helpful personal AI assistant.

Speak naturally and clearly.
Give direct and useful answers.
Keep spoken responses reasonably concise.
If the user speaks Marathi, Hindi, or English, respond in the same
language.
"""


def create_voice_token() -> str:
    """Mint a single-use token for a Gemini Live session.

    The token is valid for half an hour but can only be used once,
    and the session it opens is locked to the model and the system
    prompt configured here, so the browser cannot change them.
    """

    now = datetime.datetime.now(datetime.timezone.utc)

    token = gemini.get_client().auth_tokens.create(
        config={
            "uses": 1,
            "expire_time": now + datetime.timedelta(minutes=30),
            "new_session_expire_time": now + datetime.timedelta(minutes=1),
            "live_connect_constraints": {
                "model": settings.gemini_live_model,
                "config": {
                    "response_modalities": ["AUDIO"],
                    "system_instruction": VOICE_SYSTEM_PROMPT,
                },
            },
        }
    )

    return token.name
