# IzySafe — Production Deployment Guide

This guide deploys the **backend API**, **School Admin Web Panel**, and supporting
services (PostgreSQL, Redis, Traccar, Celery) as a self-contained Docker Compose
stack suitable for a single VPS or a container host.

---

## 1. Architecture

```
                    ┌──────────────────────────────────────────────┐
   Internet ─▶ :80  │  web (nginx)                                  │
   (browsers)       │   • serves the Admin Panel (static SPA)       │
                    │   • reverse-proxies /api → backend (same-     │
                    │     origin, so no CORS)                       │
                    │   • gzip, security headers, rate limiting     │
                    └───────────────┬──────────────────────────────┘
                                    │ (internal network)
                    ┌───────────────▼───────────┐   ┌───────────────┐
   GPS watches ─▶   │ backend (FastAPI/uvicorn) │──▶│ postgres      │
   :5023/5002/5013  │  • API + webhooks         │   │ (named vol)   │
        │           │  • SINGLETON loops        │   └───────────────┘
        ▼           │    (batch writer, device  │   ┌───────────────┐
   ┌──────────┐     │     status monitor)       │──▶│ redis (cache) │
   │ traccar  │────▶│                           │   └───────────────┘
   └──────────┘     └───────────────────────────┘
                    ┌───────────────────────────┐
                    │ celery-worker + celery-beat│  (scheduled/heavy jobs)
                    └───────────────────────────┘
```

Only **web** (:80/:443) and the **Traccar device ports** (:5023/:5002/:5013) are
exposed publicly. Postgres, Redis, the backend, and the Traccar web UI stay on the
internal Docker network.

---

## 2. Prerequisites

- A host with **Docker Engine 24+** and the **Docker Compose v2** plugin.
- A **domain** pointed at the host (e.g. `panel.yourdomain.com`), if you want TLS.
- A **Firebase** project (Blaze) service-account JSON (Realtime DB + FCM).
- Open inbound ports: `80` (and `443` for TLS), plus the GPS device ports
  `5023`, `5002`, `5013`.

Clone the repo and work inside `izysafe/`:

```bash
git clone <repo> && cd izysafe
```

---

## 3. Configure environment & secrets

```bash
cp .env.production.example .env
chmod 600 .env

# generate strong secrets
openssl rand -hex 32      # → JWT_SECRET
openssl rand -hex 32      # → TRACCAR_WEBHOOK_SECRET
openssl rand -base64 30   # → POSTGRES_PASSWORD  (also update it in DATABASE_URL)
openssl rand -base64 30   # → TRACCAR_API_PASSWORD
```

Edit `.env` and set every `__CHANGE_ME__` value. Key points:
- `POSTGRES_PASSWORD` must be identical in `DATABASE_URL` **and** in `traccar/traccar.xml`.
- `TRACCAR_WEBHOOK_SECRET` must match the `X-Traccar-Secret` header in `traccar/traccar.xml`.
- `ALLOWED_ORIGINS` — the panel is same-origin so it needs no entry; list only other
  browser origins that call the API directly.
- `SHARE_LINK_BASE_URL` must be `https://<this-host>/track` — the public Share-Link tracking
  page. nginx proxies `/track/` to the backend (already configured in `web-admin/nginx.conf`).

The third-party integrations (Firebase, OTP, Maps, Payments, R2, SMTP) are all **graceful
seams** — the stack runs without them. See **`CREDENTIALS.md`** for how to wire each one on,
what it unlocks, and how to verify it.

**Firebase credentials** — place the service-account JSON where the backend expects it:

```bash
mkdir -p backend/secrets
cp /path/to/firebase-service-account.json backend/secrets/firebase-service-account.json
```

(The `backend/secrets/` directory is gitignored and bind-mounted read-only.)

---

## 4. Build the images

```bash
docker compose -f docker-compose.prod.yml build
```

This builds:
- `izysafe-backend:prod` — runtime-only Python image, non-root, single-process uvicorn.
- `izysafe-web-admin:prod` — Vite build served by nginx (which also proxies `/api`).

---

## 5. Run database migrations

Bring up the database, then apply migrations (this is a one-off that exits):

```bash
docker compose -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
```

Re-run `alembic upgrade head` on every deploy that adds migrations (idempotent).

---

## 6. Start the stack

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps          # all healthy?
curl -fsS http://localhost/health                     # → {"status":"ok"}
```

The panel is now served at `http://<host>/`.

---

## 7. Bootstrap the first school + admin

The panel has no public sign-up. Create the first school + admin via the env-gated
seed endpoint:

1. Add a temporary secret to `.env` and restart the backend:
   ```
   SCHOOL_SEED_SECRET=<a-temporary-random-string>
   ```
   ```bash
   docker compose -f docker-compose.prod.yml up -d backend
   ```
2. Seed:
   ```bash
   curl -X POST http://localhost/api/v1/schools/seed \
     -H "Content-Type: application/json" \
     -d '{"secret":"<same-secret>","school_name":"Your School",
          "admin_email":"admin@yourschool.edu","admin_password":"<strong-password>",
          "admin_name":"Head Admin","timezone":"Asia/Kolkata"}'
   ```
3. **Remove `SCHOOL_SEED_SECRET` from `.env`** and restart the backend to disable seeding.

Log in at `http://<host>/` with those credentials.

---

## 8. TLS (HTTPS)

Pick one:

**A. Terminate TLS at the nginx `web` service** — enable the `443` port in
`docker-compose.prod.yml`, mount your certs into the container, add a `listen 443 ssl`
server block to `web-admin/nginx.conf` (with `ssl_certificate` / `ssl_certificate_key`),
redirect `80 → 443`, and uncomment the `Strict-Transport-Security` header there.

**B. Front the stack with a TLS reverse proxy** (Caddy, Traefik, or a cloud load
balancer / Cloudflare) that terminates HTTPS and forwards to `web:80`. This is the
simplest — e.g. Caddy auto-provisions Let's Encrypt certs. Keep `web` publishing only
`80` on an internal interface.

Either way, set `ENVIRONMENT=production` (already in the template) so the backend
emits HSTS and hides `/docs`.

---

## 9. Scaling & the singleton loops

The backend runs two **singleton** in-process loops (the 5s batch location writer and
the 60s device-status monitor). To scale the web tier horizontally:

- Keep **exactly one** backend instance with `RUN_BACKGROUND_LOOPS=true`.
- Run extra API replicas with `RUN_BACKGROUND_LOOPS=false` behind the nginx upstream.

Heavy/scheduled work already scales independently via **celery-worker** (add replicas
freely); **celery-beat** must stay a single instance.

---

## 10. Backups

**PostgreSQL** (the source of truth — Redis is a reconstructable cache):

```bash
# scheduled dump (add to cron)
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U izysafe izysafe | gzip > backup-$(date +%F).sql.gz

# restore
gunzip -c backup-YYYY-MM-DD.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T postgres psql -U izysafe -d izysafe
```

Also back up `backend/secrets/` and `.env` (store securely, out of git).

---

## 11. Logs & monitoring

```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml ps        # health status
```

Each container has a healthcheck; `web` and `backend` expose `/health`. Ship
`docker logs` to your aggregator (Loki/CloudWatch/etc.) as needed.

---

## 12. Updating (redeploy)

```bash
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
docker compose -f docker-compose.prod.yml up -d
```

---

## 13. Troubleshooting

| Symptom | Check |
|---|---|
| `web` 502 on `/api` | Is `backend` healthy? `docker compose ... logs backend`. |
| Login fails immediately | `JWT_SECRET` set? DB migrated? seed admin created? |
| `POSTGRES_PASSWORD must be set` | `.env` missing/incomplete — it's required. |
| Traccar positions not arriving | `TRACCAR_WEBHOOK_SECRET` matches `traccar.xml`; device ports open. |
| Firebase warning on startup | `backend/secrets/firebase-service-account.json` present + path correct. |
| Duplicate alerts / double writes | More than one backend has `RUN_BACKGROUND_LOOPS=true`. |

---

## 14. Production checklist

- [ ] All `__CHANGE_ME__` secrets replaced; `.env` is `chmod 600` and not in git.
- [ ] `ENVIRONMENT=production` (HSTS on, `/docs` hidden).
- [ ] TLS terminated (option A or B); HTTP redirects to HTTPS.
- [ ] `alembic upgrade head` run; first admin seeded; `SCHOOL_SEED_SECRET` removed.
- [ ] `SHARE_LINK_BASE_URL=https://<host>/track`; `curl https://<host>/track/x` → 200 HTML.
- [ ] Integrations wired per **`CREDENTIALS.md`** (at minimum: Traccar, Firebase, OTP).
- [ ] Postgres backups scheduled; `backend/secrets/` + `.env` backed up.
- [ ] Only `80/443` + GPS device ports exposed; Postgres/Redis internal only.
- [ ] Exactly one backend with `RUN_BACKGROUND_LOOPS=true`.

---

## 15. Parent app (Flutter) — build & release

The **parent app is a mobile client**, not part of the server Docker stack. Point it at the
deployed API (`API_BASE_URL` / `Env.apiBaseUrl` → `https://<host>/api/v1`) and build per store:

```bash
cd flutter
flutter build appbundle --release      # Android → Play Store (.aab)
flutter build ipa --release            # iOS → App Store (needs a Mac + signing)
# flutter build web --release          # optional PWA build (served separately)
```

Before a real release, wire the Firebase platform files (`google-services.json` /
`GoogleService-Info.plist`) and enable `firebase_messaging` for push — see `CREDENTIALS.md` §2.

---

## 16. Go-live sequence

1. Deploy the stack (this guide) and wire credentials — **`CREDENTIALS.md`**.
2. Validate the whole pipeline with a real GPS watch — **`HARDWARE_VALIDATION.md`**.
3. Build + submit the parent app (§15); create the first school admin (§7).
