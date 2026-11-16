"""The WhatsApp login helper page.

The sidecar prints a login QR in the terminal, which is awkward to
scan because the terminal draws it with half block characters. This
page shows the same code large enough to scan comfortably, and can
ask the sidecar for a pairing code instead when the QR is not
practical.

Everything here talks to the sidecar's small helper server on port
8787. The QR itself is never stored.
"""

import io

import httpx
import segno
from flask import Blueprint, Response, jsonify, render_template, request

from config import settings

bp = Blueprint("qr", __name__)

HELPER_TIMEOUT = 5.0


def _helper_state():
    """Ask the sidecar for the current login state.

    Never raises: if the sidecar is down the page says so instead of
    showing an error.
    """

    url = f"{settings.wa_helper_url.rstrip('/')}/qr"

    try:
        response = httpx.get(url, timeout=HELPER_TIMEOUT)
        response.raise_for_status()

        state = response.json()

        state.setdefault("qr", None)
        state.setdefault("pairingCode", None)
        state.setdefault("connected", False)
        state["error"] = None

        return state

    except httpx.HTTPError as error:
        return {
            "qr": None,
            "pairingCode": None,
            "connected": False,
            "error": str(error),
        }


def _qr_svg(data, scale=8):
    """Render a QR string as a standalone SVG image.

    `save` is used rather than `svg_inline` because a standalone SVG
    loaded through an <img> tag has to declare the SVG namespace.
    Without it the browser refuses the image and shows a broken icon
    instead of the code.
    """

    code = segno.make(data, error="m")

    buffer = io.BytesIO()

    code.save(
        buffer,
        kind="svg",
        scale=scale,
        border=4,
        dark="#1a202c",
        light="#ffffff",
    )

    return buffer.getvalue()


@bp.route("/qr", methods=["GET"])
@bp.route("/link", methods=["GET"])
def qr_page():
    """The helper page."""

    state = _helper_state()

    return render_template(
        "qr.html",
        qr=state.get("qr"),
        pairing_code=state.get("pairingCode"),
        connected=state.get("connected", False),
        sidecar_down=bool(state.get("error")),
    )


@bp.route("/qr.svg", methods=["GET"])
def qr_svg():
    """The current QR as an SVG image."""

    state = _helper_state()

    data = state.get("qr")

    if not data:
        return Response("no QR available", status=404, mimetype="text/plain")

    return Response(_qr_svg(data), mimetype="image/svg+xml")


@bp.route("/qr/status", methods=["GET"])
def qr_status():
    """The current state, for the page to poll."""

    state = _helper_state()

    return jsonify(
        {
            "qr": state.get("qr"),
            "pairingCode": state.get("pairingCode"),
            "connected": state.get("connected", False),
            "sidecarDown": bool(state.get("error")),
        }
    )


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
