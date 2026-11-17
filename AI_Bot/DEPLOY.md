# Deploying RX to a free always-on VM

This deploys the **web app + WhatsApp sidecar only**. The Telegram bot is
not started. Visitors need the password from `WEB_PASSWORD`.

Recommended host: **Oracle Cloud Always Free** (ARM Ampere A1, 4 cores /
24 GB, free forever). Ubuntu 22.04 or 24.04 works. A Google Cloud e2-micro
also works but is much slower.

## 1. Create the VM

- Create an Oracle Cloud free-tier ARM instance with Ubuntu.
- Add an ingress rule for **port 80** and **port 443** from `0.0.0.0/0`.
- Do not expose ports 5000 or 8787 — only nginx should reach them.

## 2. Install dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3-pip nginx curl git certbot python3-certbot-nginx

# Node 20 (needed by the WhatsApp sidecar)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

## 3. Install the project

```bash
sudo adduser --disabled-password rx
sudo mkdir -p /opt/rx
sudo chown rx:rx /opt/rx

# As the rx user, copy this AI_Bot folder to /opt/rx/AI_Bot
sudo -u rx bash
cd /opt/rx
# (upload or git clone the project here so the folder is /opt/rx/AI_Bot)

cd /opt/rx/AI_Bot
python3.12 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

cd whatsapp_sidecar
npm install          # postinstall applies the Baileys patch
exit
```

## 4. Configure secrets

Create `/opt/rx/AI_Bot/.env` from `.env.example` and fill in:

```ini
Gemini_API_KEY=...
TMDB_API_KEY=...
TELEGRAM_BOT_TOKEN=          # leave empty: no Telegram bot

WEB_PASSWORD=choose-a-strong-password
FLASK_SECRET_KEY=<python3 -c "import secrets; print(secrets.token_hex(32))">
WEB_HOST=127.0.0.1
WEB_PORT=5000
WEB_DEBUG=false

WA_SHARED_SECRET=<generate a long random string>
WA_PAIRING_PHONE=919423031182   # digits + country code, or leave empty to scan QR
FLASK_URL=http://127.0.0.1:5000
WA_SIDECAR_URL=http://127.0.0.1:5000
WATCH_REGION=IN
```

The `WA_SHARED_SECRET` must be the same value in both the Flask app and
the sidecar — both read the same `.env` here.

```bash
sudo chown -R rx:rx /opt/rx/AI_Bot
sudo chmod 600 /opt/rx/AI_Bot/.env
```

Create the database schema once:

```bash
cd /opt/rx/AI_Bot
./venv/bin/python -c "from database.database import init_db; init_db(); print('database ready')"
```

## 5. Run as services

```bash
sudo cp /opt/rx/AI_Bot/deploy/rx-web.service /etc/systemd/system/
sudo cp /opt/rx/AI_Bot/deploy/rx-whatsapp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rx-web rx-whatsapp
sudo systemctl status rx-web rx-whatsapp
```

Logs:

```bash
sudo journalctl -u rx-web -f
sudo journalctl -u rx-whatsapp -f
```

## 6. nginx and HTTPS

Point your domain's **A record** at the VM's public IP, then:

```bash
sudo tee /etc/nginx/sites-available/rx <<'EOF'
server {
    listen 80;
    server_name your-domain.example;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        client_max_body_size 25m;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/rx /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d your-domain.example
```

`X-Forwarded-For` matters: the login rate limiter uses it to identify
visitors behind nginx.

## 7. Link WhatsApp

Open `https://your-domain.example/qr` after logging in. Scan the QR with
WhatsApp → Linked devices, or set `WA_PAIRING_PHONE` and use the pairing
code. The session is stored in `whatsapp_sidecar/auth/` on the VM and
survives restarts.

**Data-centre IPs can be flagged by WhatsApp.** Use a spare SIM for
linking. If the account gets banned, the web app still works — only the
WhatsApp connector stops.

## 8. Verify

```bash
sudo systemctl is-active rx-web rx-whatsapp
curl -k https://your-domain.example/health
```

In the browser:

- `/` redirects to `/login` when signed out
- `/messages` shows the alerts panel
- Send a WhatsApp message from another phone, delete it, and confirm the
  alert with the original text appears on `/messages`

## Backups

Back up `/opt/rx/AI_Bot/database/chatbote.db` and
`/opt/rx/AI_Bot/whatsapp_sidecar/auth/` regularly — they contain the
archive and the WhatsApp login. Keep them private.
