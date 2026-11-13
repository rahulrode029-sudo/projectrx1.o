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

    processes = []

    for starter in (start_flask, start_telegram, start_sidecar):

        try:
            process = starter()
        except Exception as error:
            print(f"could not start: {error}")
            continue

        if process is not None:
            processes.append(process)

        time.sleep(1)

    print()
    print("All started. Press Ctrl+C to stop.")

    try:

        while True:

            for process in processes:

                if process.poll() is not None:
                    print(f"a process exited with {process.returncode}")

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
