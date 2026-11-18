# Deploying RX to a free always-on VM

This deploys the **web app + one WhatsApp sidecar per account**. Visitors
sign in with a username and password; the admin creates accounts at
`/admin/users`. Alerts stay on the website.

Recommended host: **Oracle Cloud Always Free** (ARM Ampere A1,
**2 OCPU / 12 GB**, free forever as of 2026). Ubuntu 22.04 or 24.04 works.
A Google Cloud e2-micro also works but is much slower.

> Older guides advertise 4 OCPU / 24 GB. Oracle reduced the Always Free
> Ampere allocation in 2026, so provision **2 OCPU / 12 GB** to stay free.

## 1. Create the VM

- Create an Oracle Cloud free-tier ARM instance (`VM.Standard.A1.Flex`)
  with Ubuntu. Choose the home region carefully — it cannot be changed
  later. If you see "Out of host capacity", try another availability
  domain, a smaller shape, or retry later.
- Generate/download an SSH key pair in the console; you need the private
  key to connect.
- Add ingress rules for **port 22** (your IP only, if possible), **port 80**
  and **port 443** from `0.0.0.0/0`.
- Oracle Ubuntu images also have a host firewall. After first login:
  ```bash
  sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
  sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
  ```
- Do not expose port 5000, or the sidecar helper ports (8787, 8788, …) —
  only nginx and localhost should reach them.

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

WEB_PASSWORD=choose-a-strong-password
ADMIN_USERNAME=admin
ADMIN_PASSWORD=choose-a-strong-password
ADMIN_PHONE=919876543210
PUBLIC_BASE_URL=https://your-domain.example
FLASK_SECRET_KEY=<python3 -c "import secrets; print(secrets.token_hex(32))">
WEB_HOST=127.0.0.1
WEB_PORT=5000
WEB_DEBUG=false
DISPLAY_TIMEZONE=Asia/Kolkata
RX_USE_WAITRESS=1

WA_SHARED_SECRET=<generate a long random string>
WA_PAIRING_PHONE=919423031182   # admin only; users scan their own QR
FLASK_URL=http://127.0.0.1:5000

# Forgot-password fallback (fill after your templates are approved)
MSG91_AUTH_KEY=...
MSG91_SENDER_ID=RXINFO
MSG91_OTP_TEMPLATE_ID=...
MSG91_RESET_TEMPLATE_ID=...
```

`WEB_PASSWORD` is only the bootstrap fallback for `ADMIN_PASSWORD`.
`WA_SHARED_SECRET` is read by both the app and the sidecars from the same
`.env`. `PUBLIC_BASE_URL` must be the public HTTPS domain, since reset
links are sent to phones.

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
sudo cp /opt/rx/AI_Bot/deploy/rx.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rx
sudo systemctl status rx
```

Logs:

```bash
sudo journalctl -u rx -f
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

Log in as the admin and open `https://your-domain.example/qr`. Scan the QR
with WhatsApp → Linked devices, or use the pairing code configured by
`WA_PAIRING_PHONE`. Each account has its own session folder under
`whatsapp_sidecar/auth/<user id>/` and its own helper port, so users never
share a link. Sessions survive restarts.

Other accounts are created at `/admin/users`. Share each temporary
password privately; users can change it at `/account`. When a new account
is created, the supervisor starts its sidecar within a couple of seconds
and its QR appears at `/qr` for that user.

**Data-centre IPs can be flagged by WhatsApp.** Use a spare SIM for
linking. If the account gets banned, the web app still works — only the
WhatsApp connector stops.

## 8. Verify

```bash
sudo systemctl is-active rx
curl -k https://your-domain.example/health
```

In the browser:

- `/` redirects to `/login` when signed out
- `/login` asks for a username **and** password; `/forgot-password` is public
- `/messages` shows only the signed-in user's alerts and archive
- `/admin/users` is visible only to the admin
- Send a WhatsApp message from another phone, delete it, and confirm the
  alert with the original text appears on `/messages`

## Backups

Back up `/opt/rx/AI_Bot/database/chatbote.db` and
`/opt/rx/AI_Bot/whatsapp_sidecar/auth/` regularly — they contain the
archive and the WhatsApp login. Keep them private.
