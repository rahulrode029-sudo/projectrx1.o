# RX — AI Bot Suite

A personal AI assistant with two front ends over one shared backend:

- **Telegram bot** — general AI chat plus a movie engine
- **WhatsApp sidecar** — archives messages that reach your own account,
  including ones that are deleted before you get to read them

Everything runs locally on your machine.

---

## What it does

### Telegram

```
/start /help
/movie <title>       Details, rating, cast, director, synopsis
/recommend [mood]    Suggestions — try "scary", "funny", "space"
/similar <title>    Movies like this one
/watch <title>      Where to stream it, by region
/download <title>   Free, ad-supported and download options
/search <query>     Ask anything

/contacts           Everyone who has written to you
/msg <name>         Recent messages, summarised
/read <name>        The raw text, on request
/summary <name>     What a contact has been saying
/deleted            Messages that were deleted
/mode <name>        full | summary | silent
```

### The deleted message feature

The WhatsApp sidecar captures every message the moment it arrives. When
somebody deletes it, WhatsApp sends a *revoke* event that contains no
content — only the id of the message it refers to. The bot looks that id
up in its database, flags the row, and tells you:

```
⚠️ Rahul deleted a message.

[👁 Show content]  [🔕 Ignore]
```

Tapping **Show** returns the text that was stored before the deletion.

### Privacy modes

Per contact, so you know what a message said without having to read it:

| Mode | What you get |
|---|---|
| `summary` (default) | One line: *"Rahul wants to move the 5pm meeting to 6"* |
| `full` | The message text |
| `silent` | Nothing, until you ask |

Change it any time with `/mode <name> full|summary|silent`.

---

## Setup

### 1. Python side

```powershell
cd AI_Bot
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Keys

Copy `.env.example` to `.env` and fill it in:

| Key | Where to get it |
|---|---|
| `Gemini_API_KEY` | https://aistudio.google.com/apikey |
| `TELEGRAM_BOT_TOKEN` | Message **@BotFather** on Telegram |
| `TMDB_API_KEY` | https://www.themoviedb.org/settings/api |
| `WA_SHARED_SECRET` | Any random string — the sidecar must match it |

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 3. Run

```powershell
python run.py
```

That starts the web app, the Telegram bot and the WhatsApp sidecar
together. Ctrl+C stops everything.

Run them separately if you prefer:

```powershell
python app.py            # web app on http://127.0.0.1:5000
python telegram_bot.py   # Telegram bot
```

### 4. WhatsApp sidecar

```powershell
cd whatsapp_sidecar
npm install
npm start
```

The first run prints a QR code. Scan it with the phone that has the
WhatsApp account you want to archive — it links as a second device.
The session is saved in `whatsapp_sidecar/auth/`, so you only scan once.

> Use a **spare number** if you can. Baileys is an unofficial WhatsApp
> client, and using one risks WhatsApp banning the number. A prepaid
> SIM is cheap insurance.

Once you have sent `/start` to the Telegram bot, the bot learns your
chat id and can start sending notifications.

---

## How it fits together

```
   WhatsApp (your phone)
          |
          v
   Node sidecar            captures messages + revoke events
          |
          | POST /wa/events
          v
   Flask app  <------------- shared SQLite database
          ^                        ^
          |                        |
   Telegram bot              every stored message
```

Three processes share one SQLite file, which runs in WAL mode so a
reader and a writer do not block each other.

```
AI_Bot/
├── app.py              Flask: web UI, /chat, /voice-token, /wa/*
├── telegram_bot.py     Telegram polling
├── run.py              starts everything
├── config.py           all settings in one place
├── database/           SQLAlchemy models + SQLite setup
├── models/             User, Contact, Conversation, Message, Preference
├── services/           gemini, memory, telegram, whatsapp, spam_detector
├── downloader/         movie sources and commands
│   └── sources/        tmdb_free, internet_archive, free_platforms, ...
├── routes/             chat, voice, whatsapp blueprints
├── security/           url_checker, file_checker
├── telegram_handlers/  commands, handlers, moderation
├── whatsapp_sidecar/   Node + Baileys connector
└── tests/              pytest suite
```

### Where movie data comes from

- **TMDB** — titles, ratings, cast, release dates, and which provider
  carries a title. Its watch-provider data is tagged `free`, `ads`,
  `flatrate`, `rent` and `buy` per country, refreshed daily.
- **Internet Archive** — real downloadable files, filtered to the
  `feature_films` collection so trailers and interviews are excluded.
- **Free platform registry** — MX Player, ZEE5, JioHotstar, SonyLIV,
  TVF Play, ShemarooMe, Airtel Xstream, Tubi, Plex, YouTube.

Adding another source means adding one file under `downloader/sources/`
with a `resolve()` method. Nothing else changes.

---

## Tests

```powershell
python -m pytest tests -q
```

The suite runs against a throwaway database and does not call any
external API.

---

## Notes and limits

- **Google Search grounding needs a billed API key.** On the free tier
  it returns a quota error, so `services/gemini.py` falls back to plain
  generation and the movie features use TMDB for current data instead.
- **The sidecar must be running** to catch a message before it is
  deleted. If it was offline when the message arrived, the revoke event
  often will not be replayed.
- **Telegram messages are capped at 4096 characters.** Long replies are
  split automatically.
- The bot never sends your API key to the browser. The voice feature
  uses a short-lived, single-use token instead.

---

## Troubleshooting

**`from telegram import Update` fails** — a folder named `telegram` in
the project root shadows the installed `python-telegram-bot`. The
handlers live in `telegram_handlers/` for this reason.

**The sidecar says "not logged in"** — delete `whatsapp_sidecar/auth/`
and scan the QR again.

**Telegram bot does not answer** — check the token in `.env` and make
sure only one instance is polling at a time.

**`/wa/events` returns 401** — `WA_SHARED_SECRET` differs between
`.env` and the sidecar's environment.
