"""Tests for the WhatsApp login helper page."""

import routes.qr as qr_route


def test_qr_page_renders_without_the_sidecar(client, monkeypatch):
    """The page must still render when the sidecar is down."""

    monkeypatch.setattr(
        qr_route,
        "_helper_state",
        lambda: {"qr": None, "pairingCode": None, "connected": False, "error": "boom"},
    )

    response = client.get("/qr")

    assert response.status_code == 200

    html = response.get_data(as_text=True)

    # The placeholder is shown instead of the image, so there is no
    # image element and no request to a QR that does not exist yet.
    # Only the markup is checked: the script builds the same elements
    # as strings when a new code arrives.
    markup = html.split("<script>")[0]

    assert "placeholder" in markup
    assert "<img" not in markup


def test_qr_page_is_also_reachable_at_link(client):
    assert client.get("/link").status_code == 200


def test_qr_svg_returns_404_when_there_is_no_code(client, monkeypatch):
    monkeypatch.setattr(
        qr_route,
        "_helper_state",
        lambda: {"qr": None, "pairingCode": None, "connected": False},
    )

    response = client.get("/qr.svg")

    assert response.status_code == 404


def test_qr_svg_renders_the_code(client, monkeypatch):
    monkeypatch.setattr(
        qr_route,
        "_helper_state",
        lambda: {"qr": "https://example.test/qr", "pairingCode": None, "connected": False},
    )

    response = client.get("/qr.svg")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("image/svg+xml")

    data = response.get_data()

    assert b"<svg" in data[:150]

    # A standalone SVG loaded through an <img> tag has to declare the
    # SVG namespace. Without it the browser refuses the image and
    # shows a broken icon instead of the code.
    assert b'xmlns="http://www.w3.org/2000/svg"' in data


def test_qr_page_shows_the_code_when_one_is_available(client, monkeypatch):
    monkeypatch.setattr(
        qr_route,
        "_helper_state",
        lambda: {"qr": "https://example.test/qr", "pairingCode": None, "connected": False},
    )

    html = client.get("/qr").get_data(as_text=True)

    assert "qr-frame" in html
    assert "qr.svg" in html


def test_status_reports_the_sidecar_being_down(client, monkeypatch):
    monkeypatch.setattr(
        qr_route,
        "_helper_state",
        lambda: {"qr": None, "pairingCode": None, "connected": False, "error": "boom"},
    )

    payload = client.get("/qr/status").get_json()

    assert payload["sidecarDown"] is True
    assert payload["qr"] is None


def test_pairing_requires_a_phone_number(client):
    response = client.post("/qr/pairing", json={})

    assert response.status_code == 400


def test_pairing_reports_a_sidecar_failure(client, monkeypatch):
    import httpx

    def explode(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(qr_route.httpx, "post", explode)

    response = client.post("/qr/pairing", json={"phone": "919999999999"})

    assert response.status_code == 502
