# IzySafe — Hardware Validation Guide

**Goal:** take one real 4G GPS watch from box → paired → **live tracking on the parent app**,
validating the whole pipeline (Flow A location, Flow B geofence, Flow C SOS) against real
hardware. Everything on the server side is built and unit-tested; this is the one thing that
has never been exercised with a physical device.

> Most affordable kids' watches speak **GT06** (port `5023`). TK103 (`5002`) and H02 (`5013`)
> are also supported. The exact SMS setup commands are **model-specific** — the ones below are
> the common GT06 set; check your watch's manual.

---

## 0. Prerequisites

- A **4G GT06 GPS watch** with an activated **SIM that has a data plan** (voice too, if you'll
  test audio). Note the watch's **IMEI** (printed on the back / box / under the battery).
- The IzySafe stack **deployed and reachable from the internet** (see `DEPLOY.md`), with the
  **Traccar device ports open** to the internet: `5023`, `5002`, `5013`.
- The server's **public IP or domain** (the watch dials this directly — it does *not* go
  through nginx/HTTPS; it's a raw TCP connection to Traccar).
- Traccar admin credentials wired (`CREDENTIALS.md` §1) and a parent account you can log into.

```
Watch (4G SIM) ──TCP:5023──▶ Traccar ──JSON forward──▶ backend /webhook/traccar
   │                                                        │
   │                                             Redis cache + Firebase + batch→Postgres
   ▼                                                        ▼
 GPS + GSM                                       Parent app live map (stream or poll)
```

---

## 1. Configure the watch (SMS commands)

Insert the SIM, power on, and send these SMS to the watch's number. Default password is
usually `123456` (see manual). **Replace `SERVER` with your public IP/domain.**

```
# 1. Point the watch at your Traccar server + port (GT06)
pw,123456,ip,SERVER,5023#

# 2. Set the mobile-data APN for the SIM's carrier (get APN from the carrier)
pw,123456,apn,<apn_name>#

# 3. Set an upload/heartbeat interval — every 10s while moving (tune later)
pw,123456,upload,10#

# 4. (optional) set timezone, e.g. India
pw,123456,lz,en,5.5#

# 5. Reboot to apply
pw,123456,reset#
```

The watch should reply with a confirmation SMS for each command. If it doesn't respond,
the SIM may lack SMS or the password differs — check the manual.

---

## 2. Confirm the watch reaches Traccar

Give it a minute after reboot, then check Traccar received a connection:

```bash
# The watch's IMEI should show up as a device (auto-created on first connect) OR as
# an "unknown device" connection in the logs:
docker compose -f docker-compose.prod.yml logs traccar | grep -iE "connected|<imei-last-6-digits>"

# Positions landing in Traccar's DB:
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U izysafe -d traccar -c \
  "SELECT id, uniqueid, lastupdate FROM tc_devices ORDER BY lastupdate DESC LIMIT 5;"
```

If nothing arrives: **(a)** device ports not open to the internet, **(b)** wrong server IP in
step 1, **(c)** APN wrong (no data), **(d)** SIM has no data plan.

---

## 3. Pair the watch in the parent app

This is the clean path — the app registers the device in Traccar for you:

1. Parent app → open a child → **Live Map top-bar watch icon → Devices → Add device**.
2. Enter the **IMEI** (exactly as on the watch), a name, type = **Watch**, save.
3. The backend calls `TraccarGateway.create_device(imei, name)` → the device gets a
   **`traccar_id`** (visible as *not* "Pairing…" on the card). If it still shows "Pairing…",
   Traccar creds aren't wired (`CREDENTIALS.md` §1).

> **Alternative (Traccar-first):** if the device already auto-registered in Traccar in step 2,
> pairing in the app will 409 on the IMEI only if a local row exists — it won't. The app
> create still succeeds; Traccar de-dupes by `uniqueId`. The backend also resolves incoming
> fixes by **IMEI fallback** if `traccar_id` isn't set yet, so tracking works either way.

---

## 4. Validate Flow A — live location

1. Take the watch outside (GPS needs sky) and move ~50–100 m.
2. Watch the backend ingest the forwarded position:
   ```bash
   docker compose -f docker-compose.prod.yml logs -f backend | grep -i webhook
   ```
3. Confirm the latest-fix cache is populating:
   ```bash
   docker compose -f docker-compose.prod.yml exec -T redis \
     redis-cli GET "location:child:<CHILD_ID>:latest"
   ```
4. **Parent app:** the child's marker should appear on the Live Map and move as the watch
   moves (near-instant with Firebase; within the poll interval without it).

✅ **Pass:** marker tracks the watch. Also confirm the **battery %** and **online dot** on the
device card reflect reality (online marker is 5-min sliding).

---

## 5. Validate Flow B — geofence alert

1. Create a small **Safe Zone** (e.g. 150 m circle) around your current spot with "Alert on
   exit" enabled.
2. Walk the watch **out** of the circle.
3. Expect a **geofence-exit alert** in the Alerts inbox (and an FCM push if Firebase is wired).
   First ping is baseline (no alert); the transition fires with a 5-min debounce.

---

## 6. Validate Flow C — SOS

1. **Hold the watch's SOS button** (~3s, per the watch).
2. The watch sends a GT06 alarm → Traccar event-forward → `/webhook/traccar/alarm`.
3. Expect a **full-screen SOS** in the parent app (not swipe-dismissible) + urgent push to all
   family + emergency contacts. Tap **Resolve** to clear it.

---

## 7. Validate Share Links (public page)

1. Parent app → Live Map top-bar **share-location icon → Create link** (pick 1 h).
2. Open the link (or scan its QR) in **any browser, logged out** — it hits
   `https://<host>/track/{token}` and should show the child's first name + the live marker,
   auto-refreshing. Revoke it and confirm it stops working (404).

---

## 8. Results checklist

- [ ] Watch connects to Traccar; positions in `tc_devices`.
- [ ] Device paired in app with a real `traccar_id`.
- [ ] Flow A: live marker tracks the watch; battery + online correct.
- [ ] Flow B: geofence exit → alert.
- [ ] Flow C: SOS button → full-screen alert → resolve.
- [ ] Share Link public page shows live location; revoke works.

---

## 9. Still pending after this (needs the physical watch / carrier)

- **Sound Around (F11) / Two-way Call (F12):** the `MONITOR,<phone>#` / `CALLBACK,<phone>#`
  command strings are **GT06-model-specific and unvalidated**. On a real watch, test whether
  it dials the parent; if the string differs for your model, override
  `TRACCAR_MONITOR_TEMPLATE` / `TRACCAR_CALLBACK_TEMPLATE` in `.env` (no code change).
- **Watch-Removed (F18)** + **Chat (F23) inbound:** depend on the watch's tamper-alarm and
  watch→server text transport — confirm the alarm/message strings your model emits and adjust
  the classifier sets in `webhook.py` if needed.
- **Reverse-geocoded addresses:** need `GOOGLE_MAPS_API_KEY` (`CREDENTIALS.md` §4).

---

## 10. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Watch never appears in Traccar | Device ports not open to internet; wrong server IP; APN wrong; SIM has no data. |
| In Traccar but no marker in app | Device not paired (no `traccar_id`/IMEI match); check `location:child:{id}:latest` in Redis. |
| Marker frozen / laggy | Firebase not wired → app is polling; wire Firebase (`CREDENTIALS.md` §2) for real-time. |
| Position received but "stale" | Watch clock/timezone wrong → fix drops as stale (>5 min old); set `lz` timezone. |
| SOS not full-screen | `event.forward` disabled in `traccar.xml`, or `X-Traccar-Secret` mismatch. |
| Share page shows the admin panel | `/track/` not proxied — confirm the nginx `location /track/` block and `SHARE_LINK_BASE_URL`. |
