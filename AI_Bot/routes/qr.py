"""The WhatsApp login helper page.

The sidecar prints a login QR in the terminal, which is awkward to
scan because the terminal draws it with half block characters. This
page shows the same code large enough to scan comfortably, and can
ask the sidecar for a pairing code instead when the QR is not
practical.

Everything here talks to the sidecar's small helper server on port
8787. The QR itself is never stored.
"""

import httpx
import segno
from flask import Blueprint, Response, jsonify, render_template, request

from config import settings

bp = Blueprint("qr", __name__)

HELPER_TIMEOUT = 5.0


def _helper_state():
    """Ask the sidecar for the current login state."""

    url = f"{settings.wa_helper_url.rstrip('/')}/qr"

    try:
        response = httpx.get(url, timeout=HELPER_TIMEOUT)
        response.raise_for_status()
        return response.json()

    except httpx.HTTPError as error:
        return {"error": str(error), "qr": None, "pairingCode": None}


def _qr_svg(data, scale=8):
    """Render a QR string as an SVG image."""

    code = segno.make(data, error="m")

    return code.svg_inline(
        scale=scale,
        border=4,
        dark="#1a202c",
        light="#ffffff",
    )


@bp.route("/qr", methods=["GET"])
def qr_page():
    """The helper page."""

    state = _helper_state()

    return render_template(
        "qr.html",
        qr=state.get("qr"),
        pairing_code=state.get("pairingCode"),
        connected=state.get("connected", False),
        error=state.get("error"),
    )


@bp.route("/qr.svg", methods=["GET"])
def qr_svg():
    """The current QR as an SVG image."""

    state = _helper_state()

    data = state.get("qr")

    if not data:
        return Response("no QR available", status=404, mimetype="text/plain")

    return Response(_qr_svg(data), mimetype="image/svg+xml")


@bp.route("/qr/pairing", methods=["POST"])
def pairing():
    """Ask the sidecar for an eight character pairing code."""

    payload = request.get_json(silent=True) or {}

    phone = (payload.get("phone") or "").strip()

    if not phone:
        return jsonify({"error": "phone is required"}), 400

    url = f"{settings.wa_helper_url.rstrip('/')}/pairing"

    try:
        response = httpx.post(
            url, json={"phone": phone}, timeout=15.0
        )
        response.raise_for_status()
        return jsonify(response.json())

    except httpx.HTTPError as error:
        return jsonify({"error": str(error)}), 502
