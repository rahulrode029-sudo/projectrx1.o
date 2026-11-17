"""The chat endpoint."""

from flask import Blueprint, jsonify, request

from services import gemini
from services.app_guide import APP_GUIDE, LANGUAGE_RULE

bp = Blueprint("chat", __name__)

SYSTEM_PROMPT = """
You are RX, a helpful personal AI assistant.

Your responsibilities:
- Understand the user's question before answering.
- Give accurate and useful answers.
- Explain difficult topics in simple language.
- For technical questions, provide practical examples.
- Keep answers concise unless the user asks for details.
- Do not invent information when you are unsure.
- Be respectful and professional.
""" + LANGUAGE_RULE + APP_GUIDE


@bp.route("/chat", methods=["POST"])
def chat():
    """Answer a text message with Gemini."""

    data = request.get_json(silent=True) or {}

    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "Message can not be empty."}), 400

    try:

        response = gemini.ask(user_message, system=SYSTEM_PROMPT)

        return jsonify({"response": response})

    except Exception as error:

        print(f"Error generating response: {error}")

        return jsonify({"error": "Failed to generate response."}), 500
