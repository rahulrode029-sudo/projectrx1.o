"""Start the web-only suite in one terminal.

    python run.py

Runs the Flask app plus one WhatsApp sidecar for every active account.
Accounts are read from the database every couple of seconds, so a new
user created in the admin panel gets their own sidecar (and QR page)
without restarting this launcher.

Press Ctrl+C to stop everything.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SIDECAR_DIR = BASE_DIR / "whatsapp_sidecar"
AUTH_ROOT = SIDECAR_DIR / "auth"

PYTHON = sys.executable

POLL_SECONDS = 2


def _load_env():
    """Load .env into this process so sidecars inherit it."""

    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")


def _port_free(port):
    """True when nothing is listening on the port."""

    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)

        return probe.connect_ex(("127.0.0.1", port)) != 0


def _check_ports():
    """Warn about the web port being taken."""

    if not _port_free(5000):
        print(
            "WARNING: port 5000 is already in use, so the web app may "
            "fail to start. Close whatever is using it and try again."
        )


def start_flask():
    print("starting the web app on http://127.0.0.1:5000")

    # Production uses waitress (see deploy/rx.service). Locally the
    # Flask development server is fine and gives us the reload-free log.
    if os.environ.get("RX_USE_WAITRESS", "").lower() in {"1", "true", "yes"}:
        waitress = shutil.which("waitress-serve")

        if waitress is None:
            local = BASE_DIR / "venv" / "Scripts" / "waitress-serve.exe"

            if not local.exists():
                local = BASE_DIR / "venv" / "bin" / "waitress-serve"

            if local.exists():
                waitress = str(local)

        if waitress:
            host = os.environ.get("WEB_HOST", "127.0.0.1")
            port = os.environ.get("WEB_PORT", "5000")

            return subprocess.Popen(
                [waitress, f"--host={host}", f"--port={port}", "app:app"],
                cwd=BASE_DIR,
            )

        print("RX_USE_WAITRESS is set but waitress-serve was not found")

    return subprocess.Popen([PYTHON, "app.py"], cwd=BASE_DIR)


def _node_binary():
    node = shutil.which("node")

    if not node:
        print("node was not found on PATH, skipping WhatsApp sidecars")

    return node


def _sidecar_starter(user, admin_id: int):
    """Return a starter closure for one account's sidecar."""

    def start():
        node = _node_binary()

        if not node:
            return None

        if not (SIDECAR_DIR / "node_modules").is_dir():
            print(
                "the sidecar is not installed yet, skipping it.\n"
                "  cd whatsapp_sidecar && npm install"
            )
            return None

        auth_folder = AUTH_ROOT / str(user.id)
        auth_folder.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env.update(
            {
                "RX_USER_ID": str(user.id),
                "RX_USER_TOKEN": user.wa_token or "",
                "WA_AUTH_FOLDER": str(auth_folder),
                "WA_HELPER_PORT": str(user.wa_port or 8787),
                # Only the original admin account uses the configured
                # pairing phone. New users scan the QR in their browser.
                "WA_PAIRING_PHONE": (
                    env.get("WA_PAIRING_PHONE", "") if user.id == admin_id else ""
                ),
            }
        )

        print(f"starting WhatsApp sidecar for {user.username} on port {user.wa_port}")

        return subprocess.Popen(
            [node, "index.js"], cwd=SIDECAR_DIR, env=env
        )

    return start


def _accounts():
    from services import accounts

    return accounts.active_users(), accounts.all_users(), accounts.bootstrap_admin_id()


def _stop(process):
    if process is None or process.poll() is not None:
        return

    try:
        process.terminate()
    except Exception:
        pass

    time.sleep(1)

    if process.poll() is None:
        try:
            process.kill()
        except Exception:
            pass


def main():
    _load_env()
    _check_ports()

    processes = {}
    starters = {}
    names = {}

    flask = start_flask()

    if flask is not None:
        processes["flask"] = flask
        starters["flask"] = start_flask
        names["flask"] = "the web app"

    print()
    print("All started. Press Ctrl+C to stop.")

    try:
        while True:
            active, everyone, admin_id = _accounts()
            wanted = {("wa", user.id): user for user in active}

            for key in list(processes):
                if key == "flask":
                    continue

                if key in wanted:
                    continue

                print(f"stopping sidecar for account {key[1]}")
                _stop(processes.pop(key))
                starters.pop(key, None)
                names.pop(key, None)

                # A disabled account keeps its session. A deleted one
                # does not come back, so its folder can go too.
                if key[1] not in {user.id for user in everyone}:
                    shutil.rmtree(AUTH_ROOT / str(key[1]), ignore_errors=True)

            for key, user in wanted.items():
                if key in processes:
                    continue

                starters[key] = _sidecar_starter(user, admin_id)
                names[key] = f"WhatsApp ({user.username})"
                processes[key] = starters[key]()

            for key, process in list(processes.items()):
                if process is None or process.poll() is None:
                    continue

                code = process.poll()

                print(
                    f"WARNING: {names[key]} exited with code {code}. "
                    "Restarting it."
                )

                replacement = starters[key]()

                if replacement is not None:
                    processes[key] = replacement

            time.sleep(POLL_SECONDS)

    except KeyboardInterrupt:
        print()
        print("stopping...")

    finally:
        for process in processes.values():
            _stop(process)

        print("stopped.")


if __name__ == "__main__":
    main()
