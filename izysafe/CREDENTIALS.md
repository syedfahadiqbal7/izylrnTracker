# IzySafe — Credentials & Integrations Wiring Guide

Every external integration in IzySafe is a **graceful seam**: the code is built and tested
behind a gateway that **no-ops (logs a warning) when its credentials are absent**, so the
app runs end-to-end without any of them. This guide is the checklist for turning each one
on for a real launch — where to get the credential, which env var it sets, what stays
disabled without it, and how to verify it.

> All variables go in the backend `.env` (see `.env.production.example`). After editing
> `.env`, restart the backend: `docker compose -f docker-compose.prod.yml up -d backend`.

---

## Priority order

| # | Integration | Needed for | Blocks launch? |
|---|---|---|---|
| 1 | **Traccar** (admin + webhook secret) | GPS ingest, live tracking, SOS, audio | **YES** — no tracking without it |
| 2 | **Firebase** (RTDB + FCM) | <1s live map stream + push notifications | **YES** for real-time UX |
| 3 | **OTP** (MSG91 / Twilio) | Parent login (WhatsApp/SMS OTP) | **YES** — parents can't log in |
| 4 | **Google Maps** | Reverse-geocoding (address labels) | No — maps use keyless OSM |
| 5 | **Payments** (Razorpay / Stripe) | Paid tier upgrades | No — free tier works |
| 6 | **Cloudflare R2** | Child photos, weekly PDFs | No — optional media |
| 7 | **SMTP** | School-admin password-reset emails | No — school-only |

---

## 1. Traccar (GPS middleware) — REQUIRED

Traccar decodes the GT06/TK103/H02 protocols and forwards positions to our webhook.

| Env var | Value |
|---|---|
| `TRACCAR_URL` | `http://traccar:8082` (internal compose DNS — leave as-is) |
| `TRACCAR_API_USER` | The Traccar admin email you create on first login |
| `TRACCAR_API_PASSWORD` | That admin's password |
| `TRACCAR_WEBHOOK_SECRET` | `openssl rand -hex 32` — **must match** the `X-Traccar-Secret` header in `traccar/traccar.xml` |

**Setup:** bring up Traccar, open its web UI (internal `:8082`, or tunnel to it), create the
admin account, then put those creds in `.env`. Also set the **same** `POSTGRES_PASSWORD` in
`traccar/traccar.xml` (`database.password`) and the **same** `TRACCAR_WEBHOOK_SECRET` in both
`forward.header` and `event.forward.header` there.

**Disabled without it:** `TraccarGateway.create_device` returns `null` → device pairing
still succeeds locally but the tracker isn't registered in Traccar, so no positions resolve.
Audio commands (Sound Around / Two-way Call) also no-op.

**Verify:** pair a device in the parent app → the created device should get a non-null
`traccar_id`; the device appears in the Traccar UI.

---

## 2. Firebase — Realtime DB (live stream) + FCM (push) — REQUIRED for real-time

One Firebase **Blaze**-plan project provides both the Realtime Database (the <1s live-map
stream) and Cloud Messaging (push).

| Env var | Value |
|---|---|
| `FIREBASE_CREDENTIALS_JSON` | `/app/secrets/firebase-service-account.json` (path inside the container) |
| `FIREBASE_DATABASE_URL` | e.g. `https://izysafe-prod-default-rtdb.<region>.firebasedatabase.app` |

**Setup:**
1. Firebase console → Project settings → Service accounts → **Generate new private key** → download the JSON.
2. `mkdir -p backend/secrets && cp <that>.json backend/secrets/firebase-service-account.json` (gitignored, bind-mounted read-only).
3. Enable **Realtime Database** and **Cloud Messaging** in the console; put the RTDB URL in `FIREBASE_DATABASE_URL`.
4. In the Flutter app add the platform config (`google-services.json` / `GoogleService-Info.plist`) and enable `firebase_messaging`.

**Disabled without it:** `RealtimeGateway` / `FcmGateway` no-op. The parent app falls back
to **polling** `GET /children/{id}/location/latest` (~works, just not sub-second), and no
push notifications are delivered (alerts still land in the in-app inbox).

**Verify:** startup logs show no "Firebase not configured" warning; a position update writes
to RTDB `live_locations/{child_id}`; a test alert triggers an FCM push on a real device.

---

## 3. OTP delivery — MSG91 (WhatsApp) + Twilio (SMS fallback) — REQUIRED

Parents log in with a phone OTP: WhatsApp via MSG91 first, SMS via Twilio after a 30s fallback.

| Env var | From |
|---|---|
| `MSG91_AUTH_KEY`, `MSG91_WHATSAPP_TEMPLATE` | MSG91 dashboard (auth key + approved WhatsApp template/flow id) |
| `TWILIO_SID`, `TWILIO_TOKEN`, `TWILIO_FROM_NUMBER` | Twilio console (Account SID, auth token, a verified sending number) |

**Disabled without it:** `send-otp` **logs the OTP** instead of sending it (the dev-OTP
recipe). Fine for testing; **must be configured before real users** or nobody can log in.

**Verify:** `POST /api/v1/auth/send-otp` for your own number → you receive the code on
WhatsApp/SMS (not just in the logs).

---

## 4. Google Maps — reverse-geocoding — optional

| Env var | From |
|---|---|
| `GOOGLE_MAPS_API_KEY` | Google Cloud console (enable Geocoding API; restrict the key) |

**Disabled without it:** `GeocodingGateway` no-ops → safe-zone/address labels fall back to
raw coordinates. **Maps themselves need no key** — both apps render keyless OpenStreetMap
tiles (map layer is isolated for a later swap to `google_maps_flutter`).

**Verify:** create a safe zone without an address → it gets a geocoded street label.

---

## 5. Payments — Razorpay (India) + Stripe (UAE) — optional (paid tiers)

Activation is **webhook-driven**, so the `*_WEBHOOK_SECRET` values are the critical ones.

| Env var | From |
|---|---|
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | Razorpay dashboard → API keys |
| `RAZORPAY_WEBHOOK_SECRET` | Razorpay → Webhooks (point it at `/api/v1/webhook/razorpay`) |
| `RAZORPAY_PLAN_BASIC`, `RAZORPAY_PLAN_PREMIUM` | Razorpay recurring **Plan** IDs |
| `STRIPE_SECRET_KEY` | Stripe dashboard → API keys |
| `STRIPE_WEBHOOK_SECRET` | Stripe → Webhooks (point it at `/api/v1/webhook/stripe`) |
| `STRIPE_PRICE_BASIC`, `STRIPE_PRICE_PREMIUM` | Stripe recurring **Price** IDs |

**Disabled without it:** `POST /subscriptions/checkout` returns 502 (gateway unconfigured);
everyone stays on the free tier. Webhook + expiry-sweep paths are already live-verified.

**Verify:** run a gateway test-mode checkout → the signed webhook flips the subscription to
`active` (idempotent per event id).

---

## 6. Cloudflare R2 — media storage — optional

| Env var | From |
|---|---|
| `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET`, `R2_ENDPOINT` | Cloudflare R2 dashboard (S3-compatible) |

**Disabled without it:** child-photo upload + weekly-PDF storage are unavailable (both
deferred features). No impact on core tracking.

---

## 7. SMTP — school-admin emails — optional

| Env var | Notes |
|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_USE_TLS` | Any SMTP relay (SES, Postmark, Gmail app-password, …) |

**Disabled without it:** `EmailGateway` no-ops → school-admin password-reset links are logged,
not emailed. No impact on the parent app.

---

## Post-wiring smoke test

```bash
# 1. Backend healthy, no "not configured" warnings you didn't expect
docker compose -f docker-compose.prod.yml logs backend | grep -i "not configured"

# 2. OTP actually delivered
curl -X POST https://panel.yourdomain.com/api/v1/auth/send-otp \
  -H "Content-Type: application/json" -d '{"phone":"+91XXXXXXXXXX"}'

# 3. Public share page reachable (Share Links)
curl -sS -o /dev/null -w "%{http_code}\n" https://panel.yourdomain.com/track/anytoken   # → 200
```

Then run the end-to-end device test in **`HARDWARE_VALIDATION.md`**.
