# IzySafe — Staging Deployment Runbook (Ubuntu 22.04)

Copy-paste runbook for a single VPS. Companion to `DEPLOY.md` (reference) and
`CREDENTIALS.md` (integrations). Run everything as your SSH user (`ubuntu`); it uses
`sudo` where root is needed.

**Replace these placeholders wherever they appear:**
- `<VPS_IP>` — your server's public IP
- `<DOMAIN>` — e.g. `panel.izysafe.com` (or skip TLS/domain steps for IP-only staging)

> Report back after each **STEP**; if anything errors, paste the output and stop.

---

## STEP 0 — DNS & ports (before you start)

- If using a domain: create an **A record** `<DOMAIN> → <VPS_IP>` (do this now so DNS propagates).
- In your VPS provider's firewall/security-group, open inbound: **22, 80, 443, 5023, 5002, 5013**.
  (5023/5002/5013 are the GPS device ports — watches dial in on these.)

---

## STEP 1 — Server setup + Docker

```bash
# update base packages
sudo apt-get update && sudo apt-get -y upgrade

# install Docker Engine + Compose plugin (official repo)
sudo apt-get -y install ca-certificates curl git ufw
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# run docker without sudo (log out/in after, or run `newgrp docker`)
sudo usermod -aG docker $USER
newgrp docker

# verify
docker --version && docker compose version
```

Host firewall (defense in depth — provider firewall still applies):

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 5023/tcp
sudo ufw allow 5002/tcp
sudo ufw allow 5013/tcp
sudo ufw --force enable
sudo ufw status
```

**✅ Checkpoint:** `docker compose version` prints a version; `ufw status` shows the ports.

---

## STEP 2 — Clone the repo

```bash
cd ~
git clone https://github.com/syedfahadiqbal7/izylrnTracker.git
cd izylrnTracker/izysafe        # <-- ALL commands below run from here
```

**✅ Checkpoint:** `ls docker-compose.prod.yml` exists.

---

## STEP 3 — Generate secrets

Generate four secrets and **save them somewhere safe** — you'll paste them into `.env`
and `traccar.xml` in the next steps:

```bash
echo "JWT_SECRET             = $(openssl rand -hex 32)"
echo "TRACCAR_WEBHOOK_SECRET = $(openssl rand -hex 32)"
echo "POSTGRES_PASSWORD      = $(openssl rand -base64 30 | tr -d '/+=' | head -c 30)"
echo "TRACCAR_API_PASSWORD   = $(openssl rand -base64 30 | tr -d '/+=' | head -c 30)"
```

> `POSTGRES_PASSWORD` is stripped of `/ + =` so it's safe inside a URL and XML.

---

## STEP 4 — Create and fill `.env`

```bash
cp .env.production.example .env
chmod 600 .env
nano .env      # (or vim)
```

Set these (using the secrets from STEP 3):

```ini
ENVIRONMENT=production
RUN_BACKGROUND_LOOPS=true

POSTGRES_DB=izysafe
POSTGRES_USER=izysafe
POSTGRES_PASSWORD=<the POSTGRES_PASSWORD you generated>
# the SAME password must appear inside DATABASE_URL:
DATABASE_URL=postgresql+asyncpg://izysafe:<same POSTGRES_PASSWORD>@postgres:5432/izysafe

REDIS_URL=redis://redis:6379/0

JWT_SECRET=<the JWT_SECRET you generated>
JWT_ALGORITHM=HS256
JWT_ACCESS_EXPIRE_MINUTES=1440
JWT_REFRESH_EXPIRE_DAYS=30

# If you have a domain use https://<DOMAIN>; for IP-only staging use http://<VPS_IP>
ALLOWED_ORIGINS=https://<DOMAIN>
BACKEND_URL=https://<DOMAIN>
SHARE_LINK_BASE_URL=https://<DOMAIN>/track

TRACCAR_URL=http://traccar:8082
# Set these AFTER STEP 9 (creating the Traccar admin). Leave the password blank for now.
TRACCAR_API_USER=admin@<DOMAIN>
TRACCAR_API_PASSWORD=
TRACCAR_WEBHOOK_SECRET=<the TRACCAR_WEBHOOK_SECRET you generated>

# Firebase — fill the RTDB URL after STEP 5 (file goes in backend/secrets)
FIREBASE_CREDENTIALS_JSON=/app/secrets/firebase-service-account.json
FIREBASE_DATABASE_URL=

# OTP — fill when you have the keys (STEP 11). Blank = OTP logged, not sent.
MSG91_AUTH_KEY=
TWILIO_SID=
TWILIO_TOKEN=
TWILIO_FROM_NUMBER=

# Temporary bootstrap secret for creating the first school admin (removed in STEP 10)
SCHOOL_SEED_SECRET=<any random string, e.g. output of: openssl rand -hex 16>
```

> **IP-only staging:** replace the three `https://<DOMAIN>` lines with `http://<VPS_IP>`
> and `SHARE_LINK_BASE_URL=http://<VPS_IP>/track`. You can switch to the domain later.

---

## STEP 5 — Traccar config + Firebase secret

**5a. Edit `traccar/traccar.xml`** — three values must match `.env`:

```bash
nano traccar/traccar.xml
```
- `database.password` → your **POSTGRES_PASSWORD**
- both `forward.header` and `event.forward.header` (`X-Traccar-Secret: ...`) → your **TRACCAR_WEBHOOK_SECRET**

**5b. Firebase service-account JSON** (once you have it from the Firebase console):

```bash
mkdir -p backend/secrets
# upload the file from your laptop, e.g.:
#   scp firebase-service-account.json ubuntu@<VPS_IP>:~/izylrnTracker/izysafe/backend/secrets/
ls -l backend/secrets/firebase-service-account.json
```
Then put the RTDB URL in `.env` → `FIREBASE_DATABASE_URL=https://<project>-default-rtdb.<region>.firebasedatabase.app`.

> Don't have Firebase yet? You can proceed — the app falls back to REST polling and skips
> push. Wire it later (`CREDENTIALS.md` §2) and `docker compose ... up -d backend`.

---

## STEP 6 — Build images

```bash
docker compose -f docker-compose.prod.yml build
```

**✅ Checkpoint:** ends with `izysafe-backend:prod Built` and `izysafe-web-admin:prod Built`.

---

## STEP 7 — Database + migrations

```bash
# bring up just the DB first
docker compose -f docker-compose.prod.yml up -d postgres
sleep 8
docker compose -f docker-compose.prod.yml ps postgres     # should be healthy

# apply all migrations (one-off container that exits)
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

**✅ Checkpoint:** the last migration line reads `... -> 0020_chat_i18n_seed`.

---

## STEP 8 — Bring up the stack + health smoke test

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps          # all Up / healthy

# API liveness (through nginx)
curl -fsS http://localhost/health                      # -> {"status":"ok"}
# Public share track page (should return HTML)
curl -s -o /dev/null -w "track page: %{http_code}\n" http://localhost/track/x   # -> 200
```

**✅ Checkpoint:** `/health` returns ok, track page returns 200. If `web` 502s on `/api`,
check `docker compose -f docker-compose.prod.yml logs backend`.

---

## STEP 9 — Create the Traccar admin + wire its creds

Traccar's web UI (`:8082`) is internal-only. From **your laptop**, open an SSH tunnel:

```bash
# on your LAPTOP (not the server):
ssh -L 8082:localhost:8082 ubuntu@<VPS_IP>
```
Then in your laptop browser open **http://localhost:8082** → register the first user
(this first account becomes the Traccar admin). Use the email/password you want.

Back **on the server**, put those into `.env` and restart the backend:

```bash
nano .env      # set TRACCAR_API_USER + TRACCAR_API_PASSWORD to the account you just made
docker compose -f docker-compose.prod.yml up -d backend celery-worker celery-beat
```

**✅ Checkpoint:** `docker compose ... logs backend | grep -i traccar` shows no
"Traccar API not configured" warning.

---

## STEP 10 — Seed the first school admin

The panel has no public sign-up. Create the first school + admin via the env-gated seed
(the `SCHOOL_SEED_SECRET` you set in STEP 4):

```bash
curl -s -X POST http://localhost/api/v1/schools/seed \
  -H "Content-Type: application/json" \
  -d '{
    "secret":"<your SCHOOL_SEED_SECRET>",
    "school_name":"Your School",
    "admin_email":"admin@yourschool.edu",
    "admin_password":"<a-strong-password-min-8>",
    "admin_name":"Head Admin",
    "timezone":"Asia/Kolkata"
  }'
```

Then **disable seeding** (security): remove `SCHOOL_SEED_SECRET` from `.env` and restart:

```bash
sed -i '/^SCHOOL_SEED_SECRET=/d' .env
docker compose -f docker-compose.prod.yml up -d backend
```

**✅ Checkpoint:** the seed call returned `201` with the school + admin; you can log in at
`http://<VPS_IP>/` (or your domain) with those credentials.

---

## STEP 11 — OTP keys (when ready)

Parents log in by phone OTP. Until these are set, `send-otp` **logs** the code instead of
sending it (fine for testing, but real users can't log in). Add to `.env` and restart:

```bash
nano .env      # set MSG91_AUTH_KEY (+ MSG91_WHATSAPP_TEMPLATE) and/or TWILIO_SID / TWILIO_TOKEN / TWILIO_FROM_NUMBER
docker compose -f docker-compose.prod.yml up -d backend
```

---

## STEP 12 — TLS / HTTPS (needs a domain)

Simplest self-hosted option — **Caddy** in front (auto Let's Encrypt). Remap the web
container to a local port, then let Caddy terminate TLS:

```bash
# 12a. Remap web to localhost:8080 via an override file
cat > docker-compose.override.yml <<'YAML'
services:
  web:
    ports: !override
      - "127.0.0.1:8080:80"
YAML
docker compose -f docker-compose.prod.yml up -d web

# 12b. Install Caddy and point it at the web container
sudo apt-get -y install debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update && sudo apt-get -y install caddy

echo "<DOMAIN> {
    reverse_proxy 127.0.0.1:8080
}" | sudo tee /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Now `.env` already points at `https://<DOMAIN>` (STEP 4). Restart the backend so it emits
HSTS / hides docs and issues correct share URLs:

```bash
docker compose -f docker-compose.prod.yml up -d backend
```

**✅ Checkpoint:** `curl -fsS https://<DOMAIN>/health` → ok; `https://<DOMAIN>/track/x` → 200.

> Alternative: if your domain is on **Cloudflare**, just proxy the DNS record (orange cloud)
> with SSL=Full — no server TLS config needed. Skip 12a/12b and keep `web` on `:80`.

---

## STEP 13 — Final smoke test

```bash
# from the server
curl -fsS http://localhost/health
curl -s -o /dev/null -w "%{http_code}\n" http://localhost/track/x
docker compose -f docker-compose.prod.yml ps        # everything healthy
```

- Open the panel in a browser (`https://<DOMAIN>/` or `http://<VPS_IP>/`), log in with the
  seeded admin, toggle **dark mode**, switch **language** (en/hi/ar) → confirm it works.
- Backend `/docs` should be **hidden** (404) in production — good.

---

## STEP 14 — Post-deploy

- **Backups (cron):**
  ```bash
  docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U izysafe izysafe | gzip > ~/backup-$(date +%F).sql.gz
  ```
  Also back up `.env` and `backend/secrets/` off-server.
- **Logs:** `docker compose -f docker-compose.prod.yml logs -f backend`
- **Redeploy on new commits:**
  ```bash
  git pull
  docker compose -f docker-compose.prod.yml build
  docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
  docker compose -f docker-compose.prod.yml up -d
  ```
- **Hardware validation** (real GPS watch, end-to-end): follow `HARDWARE_VALIDATION.md`.

---

## Troubleshooting quick table

| Symptom | Check |
|---|---|
| `POSTGRES_PASSWORD must be set` | `.env` missing/incomplete, or you didn't run from `izysafe/`. |
| `web` 502 on `/api` | `docker compose ... logs backend` — is it healthy? DB migrated? |
| Traccar positions not arriving | `TRACCAR_WEBHOOK_SECRET` in `.env` must equal both headers in `traccar.xml`; device ports open. |
| "Traccar API not configured" | `TRACCAR_API_USER/PASSWORD` unset (STEP 9). |
| Firebase warning at startup | `backend/secrets/firebase-service-account.json` present + `FIREBASE_DATABASE_URL` set. |
| OTP never received | `MSG91_AUTH_KEY` / Twilio creds not set (STEP 11). |
| Share page shows the panel, not the map | `SHARE_LINK_BASE_URL` = `https://<DOMAIN>/track` and nginx `/track/` proxy present (it is). |
