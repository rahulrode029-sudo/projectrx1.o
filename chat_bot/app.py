from flask import Flask, render_template, request, jsonify
from google import genai
from dotenv import load_dotenv
import os

print("APP.PY IS RUNNING")

load_dotenv()

app = Flask(__name__)

_client = None


def get_client():
    """Build the Gemini client on first use.

    Doing this lazily means a missing API key fails when a request
    comes in, instead of crashing the whole app at import time.
    """

    global _client

    if _client is None:

        api_key = os.getenv("Gemini_API_KEY")

        if not api_key:
            raise RuntimeError("Gemini_API_KEY is not set in .env")

        _client = genai.Client(api_key=api_key)

    return _client


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json(silent=True) or {}

    user_message = (data.get("message") or "").strip()

    if not user_message:
        return jsonify({"error": "Message is required."}), 400

    try:

        response = get_client().models.generate_content(
            model="gemini-3.6-flash",
            contents=user_message
        )

        return jsonify({"response": response.text})

    except Exception as e:

        print(f"Error generating response: {e}")

        return jsonify({"error": "Failed to generate response."}), 500


if __name__ == "__main__":
    app.run(debug=True)
