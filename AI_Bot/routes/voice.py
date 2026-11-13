"""The voice token endpoint.

The browser talks to Gemini Live directly, so it needs a short-lived
token rather than the API key. The key never leaves the server.
"""

from flask import Blueprint, jsonify

from services import voice

bp = Blueprint("voice", __name__)


@bp.route("/voice-token", methods=["POST"])
def voice_token():
    """Mint a single-use token for a Gemini Live session."""

    try:

        token = voice.create_voice_token()

        print("Voice token created successfully")

        return jsonify({"token": token})

    except Exception as error:

        print("Error generating voice token:", error)

        return jsonify({"error": str(error)}), 500
