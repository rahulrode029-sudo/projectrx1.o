# RX — private WhatsApp archive

A password-protected website where every user links their own WhatsApp and
sees only their own archive. Messages are captured the moment they arrive,
and a deleted message stays visible in red with its original text.

There is no Telegram bot, no email delivery, and no movie pages. Alerts
appear on this website only.

---

## What it does

- **Separate account per user.** The admin creates accounts at `/admin/users`;
  there is no public signup. Each account gets its own WhatsApp session,
  local helper port, contacts, messages and alerts.
- **Deleted messages.** When somebody deletes a message, the revoke event
  flags the stored copy and writes a web alert. The original text stays
  available in the Messages page.
- **Assistant.** Ask “how to use this application” in any language and the
  built-in guide explains the app. It never invents other products.
- **Voice.** Short-lived tokens are used for the browser voice feature; the
  API key is never sent to the browser.
- **Password recovery.** `/forgot-password` sends a one-time reset link and
  the username to the account's phone — WhatsApp first, MSG91 SMS fallback.
  Old passwords are never sent.

---

## Run locally

```powershell
cd AI_Bot
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd whatsapp_sidecar
npm install
cd ..

copy .env.example .env
# fill in .env: Gemini_API_KEY, FLASK_SECRET_KEY, WA_SHARED_SECRET,
# ADMIN_PASSWORD, ADMIN_PHONE, PUBLIC_BASE_URL, MSG91_* values

python run.py
```

Open **http://127.0.0.1:5000/login**.

### One-click local start (Windows)

Double-click `START_RX.bat` (or the **RX Local** shortcut on the Desktop).
It detects the PC's LAN IP, updates `WEB_HOST` and `PUBLIC_BASE_URL`
automatically, then starts the app and prints both URLs:

```
PC    : http://127.0.0.1:5000/login
Mobile: http://192.168.x.x:5000/login   (same Wi-Fi)
```

Close the console window to stop the app. For mobile access, run
`ALLOW_FIREWALL.bat` (or **RX Allow Firewall** on the Desktop) once with
**Run as administrator** to open port 5000 on the local network.

`run.py` starts the web app and one WhatsApp sidecar for every active
account. A newly created user gets their own sidecar within a couple of
seconds without restarting the launcher. Ctrl+C stops everything.

### Link WhatsApp

Open **http://127.0.0.1:5000/qr**. Scan the QR with WhatsApp →
**Settings → Linked devices → Link a Device**, or use the eight-character
pairing code. Set `WA_PAIRING_PHONE` in `.env` to generate the admin code
automatically.

`npm install` applies a patch to Baileys automatically. This matters:
WhatsApp added a `companion_reg_refresh` stage that no published Baileys
release handles, so pairing fails with *“Couldn't link device”* without the
patch in `patches/`.

> Use a spare number if you can. Baileys is an unofficial WhatsApp client.

### Track WhatsApp sessions

On the **Messages** page every contact has an eye button. Turn it on only
for contacts whose WhatsApp active times you want to record. The sidecar
then subscribes to their presence and stores each window as:

```
Amit Sharma · 24 Nov 11:10 → 11:25 · 15 min
```

The same entry appears as a chip above the messages, in a compact strip
on the Chat page, and as an `online_session` alert. When nothing has been
recorded yet, the page shows a short hint instead of an empty box. Times
are saved in UTC and shown in the display time zone. Very short blips are
ignored and nearby sessions are merged.

Tracking stops working while the app is closed, and WhatsApp never sends
presence for contacts who hide their online/last-seen status from your
linked account.

---

## Configuration

See `.env.example` for every setting. Important ones:

| Setting | Purpose |
|---|---|
| `Gemini_API_KEY` | AI replies and summary alerts |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | First account, created on first start |
| `FLASK_SECRET_KEY` | Signs session cookies |
| `WA_SHARED_SECRET` | Shared between the web app and the sidecars |
| `WA_PAIRING_PHONE` | Admin's number for automatic pairing code |
| `PUBLIC_BASE_URL` | Public HTTPS domain used in reset links |
| `MSG91_AUTH_KEY`, `MSG91_*_TEMPLATE_ID` | SMS fallback for recovery |
| `DISPLAY_TIMEZONE` | Time zone shown on the website (stored as UTC) |
| `RX_USE_WAITRESS` | Set to `1` on the VM |

For a production VM with nginx, HTTPS and systemd, follow **DEPLOY.md**.

---

## Layout

```
AI_Bot/
├── app.py              Flask: web pages, /chat, /voice-token, /wa/*
├── run.py              starts the web app + one sidecar per user
├── config.py           settings from .env
├── database/           SQLite setup
├── models/             accounts, contacts, conversations, messages, alerts, presence sessions
├── routes/             auth, admin, alerts, chat, contacts, qr, recovery, voice, whatsapp
├── services/           accounts, recovery, memory, gemini, whatsapp, presence, spam_detector, app_guide
├── security/           URL and file checks
├── templates/          web pages
├── static/             styles and browser scripts
├── whatsapp_sidecar/   Node + Baileys connector, per-user auth folders
├── deploy/rx.service   production systemd unit
├── DEPLOY.md           VM deployment guide
└── tests/              pytest suite
```

---

## Tests

```powershell
python -m pytest tests -q
```

From `whatsapp_sidecar/`:

```powershell
node --test session_check.test.js
```

The suite uses a throwaway database and makes no external API calls.

---

## Notes

- The sidecar must be running to catch a message before it is deleted. If it
  was offline when the message arrived, the revoke event is usually not
  replayed.
- Only post-link text and captions are archived. Media files and older
  history are not.
- Back up `database/chatbote.db` and `whatsapp_sidecar/auth/` regularly.
