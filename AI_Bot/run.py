"""Start the whole suite in one terminal.

    python run.py

Runs three processes:

  * the Flask app        (web UI, chat, voice, WhatsApp intake)
  * the Telegram bot     (commands and answers)
  * the WhatsApp sidecar (only if node and the sidecar are installed)

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

PYTHON = sys.executable


def _load_env():
    """Load .env into this process so the sidecar inherits it."""

    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")


def _port_free(port):
    """True when nothing is listening on the port."""

    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)

        return probe.connect_ex(("127.0.0.1", port)) != 0


def _check_ports():
    """Warn about ports that are already taken."""

    for port, name in ((5000, "the web app"), (8787, "the WhatsApp helper")):

        if not _port_free(port):
            print(
                f"WARNING: port {port} is already in use, so {name} may "
                f"fail to start. Close whatever is using it and try again."
            )


def start_flask():
    print("starting the web app on http://127.0.0.1:5000")

    return subprocess.Popen([PYTHON, "app.py"], cwd=BASE_DIR)


def start_telegram():
    print("starting the Telegram bot")

    return subprocess.Popen([PYTHON, "telegram_bot.py"], cwd=BASE_DIR)


def start_sidecar():
    """Start the WhatsApp sidecar, if it can be started."""

    node = shutil.which("node")

    if not node:
        print("node was not found on PATH, skipping the WhatsApp sidecar")
        return None

    if not (SIDECAR_DIR / "node_modules").is_dir():
        print(
            "the sidecar is not installed yet, skipping it.\n"
            "  cd whatsapp_sidecar && npm install"
        )
        return None

    print("starting the WhatsApp sidecar")

    return subprocess.Popen([node, "index.js"], cwd=SIDECAR_DIR)


def main():
    _load_env()

    _check_ports()

    processes = []
    names = {}

    for name, starter in (
        ("the web app", start_flask),
        ("the Telegram bot", start_telegram),
        ("the WhatsApp sidecar", start_sidecar),
    ):

        try:
            process = starter()
        except Exception as error:
            print(f"could not start {name}: {error}")
            continue

        if process is not None:
            processes.append(process)
            names[process.pid] = name

        time.sleep(1)

    print()
    print("All started. Press Ctrl+C to stop.")

    try:

        while True:

            for process in processes:

                code = process.poll()

                if code is not None and process.pid in names:
                    print(
                        f"WARNING: {names[process.pid]} exited with code "
                        f"{code}. Everything else is still running."
                    )
                    del names[process.pid]

            time.sleep(2)

    except KeyboardInterrupt:

        print()
        print("stopping...")

    finally:

        for process in processes:

            if process.poll() is None:

                try:
                    process.terminate()
                except Exception:
                    pass

        time.sleep(1)

        for process in processes:

            if process.poll() is None:

                try:
                    process.kill()
                except Exception:
                    pass

    print("stopped.")


if __name__ == "__main__":
    main()
