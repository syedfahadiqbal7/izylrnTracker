# IzySafe — Hardware Spike Runbook (GT06 Watch ↔ Traccar)

> **Goal of this spike:** de-risk the device layer *before* we build the live-location
> pipeline (Sprint 2) and the audio features (Sprint 7). Concretely, prove three things:
> 1. A GT06 watch (or a simulated GT06 client) **connects to Traccar on port 5023** and **registers**.
> 2. Traccar **receives GPS positions** from it.
> 3. The **`MONITOR` (Sound Around)** and **`CALLBACK` (Two-way Call)** commands are delivered
>    to the watch — confirming the locked "no media server" audio decision (CLAUDE.md §3.12) is viable.
>
> **Prerequisite:** the dev stack is running (`docker compose up -d`). Traccar is on
> `localhost:8082` (UI/API) and listening for GT06 on `:5023`.

---

## 0. One-time Traccar admin setup

Traccar needs an admin account to use its REST API (device list, commands).

1. Open **http://localhost:8082** in a browser.
2. Register the first account → it becomes the **admin** (Traccar makes the first user admin).
3. Put those credentials in `.env` so the backend can call Traccar later:
   ```
   TRACCAR_API_USER=admin@izysafe.local
   TRACCAR_API_PASSWORD=<the password you just set>
   ```
4. Quick API sanity check (replace creds):
   ```bash
   curl -u admin@izysafe.local:PASSWORD http://localhost:8082/api/server
   ```
   Expect a JSON server object (HTTP 200).

---

## 1. Register the device in Traccar

Traccar keys devices by **IMEI**. Add the watch's IMEI (printed on the watch / box / `*#06#`).

**Via UI:** Settings → Devices → **+** → set a name + the **IMEI** as the unique identifier.

**Via API:**
```bash
curl -u admin@izysafe.local:PASSWORD -X POST http://localhost:8082/api/devices \
  -H 'Content-Type: application/json' \
  -d '{"name":"Spike Watch","uniqueId":"<IMEI_15_DIGITS>"}'
```
Note the returned numeric `id` — that's the Traccar `deviceId` used for commands below.

---

## 2A. Connect a REAL GT06 watch (port 5023)

GT06 watches are configured by **SMS to the watch SIM** (default command password is usually
`123456`). The exact syntax is **vendor-specific** — try these common GT06 variants and keep the
one your model accepts (recording the winner is part of this spike):

```
# Point the watch at your Traccar server (use a PUBLIC IP/domain if the watch is on cellular)
pw,123456,ip,<SERVER_IP_OR_DOMAIN>,5023#
# alt syntaxes seen in the wild:
SERVER,1,<SERVER_IP_OR_DOMAIN>,5023,0#
ip,<SERVER_IP_OR_DOMAIN>,5023#

# Set the SIM's mobile-data APN (carrier-specific, e.g. "airtelgprs.com", "etisalat")
pw,123456,apn,<APN_NAME>#

# Upload interval = 30s (matches our F1 spec)
pw,123456,upload,30#
pw,123456,s:30#          # alt

# Reboot to apply, then query status
pw,123456,reset#
pw,123456,ts#            # returns IMEI, server, APN, GPS fix — verify settings stuck
```

> ⚠️ The watch reaches the server over the **cellular network**, so `<SERVER_IP>` must be a
> **public** address (your VPS, or a tunnel like `ngrok tcp 5023` / Cloudflare Tunnel for local
> testing). `localhost` only works for the simulator in §2B.

Then take the watch **outside** for a clear-sky GPS fix (30–90s).

---

## 2B. No watch yet? Simulate a GT06 client (proves ingestion locally)

This sends a real **GT06 login packet** (and an optional location packet) straight to `:5023`,
so the device shows up in Traccar without hardware. Save as `tools/gt06_sim.py` and run with the
**same IMEI** you registered in §1.

```python
import socket, sys, time

def crc16_x25(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if (crc & 1) else (crc >> 1)
    return (crc ^ 0xFFFF) & 0xFFFF

def frame(proto: int, content: bytes, serial: int) -> bytes:
    body = bytes([proto]) + content + serial.to_bytes(2, "big")
    length = len(body) + 2                      # +2 for the CRC bytes
    payload = bytes([length]) + body
    crc = crc16_x25(payload)
    return b"\x78\x78" + payload + crc.to_bytes(2, "big") + b"\x0d\x0a"

def login_packet(imei: str, serial: int = 1) -> bytes:
    imei_bcd = bytes.fromhex(imei.rjust(16, "0"))   # 15-digit IMEI -> 8 BCD bytes
    return frame(0x01, imei_bcd, serial)

def location_packet(lat: float, lng: float, serial: int = 2) -> bytes:
    t = time.gmtime()
    dt = bytes([t.tm_year % 100, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec])
    sats = bytes([0xC4])                              # hi nibble=len, lo nibble=sat count
    lat_v = int(round(abs(lat) * 30000 * 60)).to_bytes(4, "big")
    lng_v = int(round(abs(lng) * 30000 * 60)).to_bytes(4, "big")
    speed = bytes([0])
    course = (0x0008 | (0 & 0x03FF)).to_bytes(2, "big")  # 0x0008 = GPS positioned flag
    content = dt + sats + lat_v + lng_v + speed + course
    return frame(0x12, content, serial)

if __name__ == "__main__":
    imei = sys.argv[1]                               # e.g. 123456789012345
    host, port = (sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"), 5023
    s = socket.socket(); s.connect((host, port))
    s.sendall(login_packet(imei)); print("login sent"); time.sleep(1)
    s.sendall(location_packet(18.5204, 73.8567))     # Pune
    print("location sent"); time.sleep(1); s.close()
```
```bash
python tools/gt06_sim.py 123456789012345 127.0.0.1
```
> CRC is **CRC16/X-25** (init 0xFFFF, poly reflected 0x8408, xorout 0xFFFF) — the exact variant
> Traccar's GT06 decoder expects. The login packet alone is enough to make the device go **online**.

---

## 3. Verify the device appears + sends positions (Traccar side)

```bash
# Device list — look for "status":"online" and a recent "lastUpdate"
curl -u admin@izysafe.local:PASSWORD http://localhost:8082/api/devices

# Latest position(s) for the device id from §1
curl -u admin@izysafe.local:PASSWORD "http://localhost:8082/api/positions?deviceId=<ID>"
```
Or in the **UI**: the device turns **green (online)** and a marker appears on the map.

**Direct DB check (Traccar's own schema, separate `traccar` DB):**
```bash
docker exec izysafe-postgres psql -U izysafe -d traccar -c \
  "SELECT id, deviceid, latitude, longitude, speed, servertime \
   FROM tc_positions ORDER BY servertime DESC LIMIT 5;"
```

### ✅ Success criteria for Steps 1–3
- Device shows **online** in Traccar within ~60s of connecting.
- `tc_positions` gains rows with **plausible lat/lng** (matches where the watch is / the simulated Pune coords).
- `servertime` is current; `valid=true` once there's a real GPS fix.

---

## 4. Test `MONITOR` (Sound Around) and `CALLBACK` (Two-way Call)

These are sent through **Traccar's command API** while the device is **online** — this is exactly
the path the backend will use in Sprint 7 (no media server). The exact command *string* is
**model-specific**; finding the one your watch obeys **is the deliverable of this step**.

```bash
# Sound Around — the watch silently calls the parent number back (ambient listen)
curl -u admin@izysafe.local:PASSWORD -X POST http://localhost:8082/api/commands \
  -H 'Content-Type: application/json' \
  -d '{"deviceId":<ID>,"type":"custom","attributes":{"data":"MONITOR,<PARENT_PHONE>#"}}'

# Two-way Call — the watch dials the parent for a duplex call
curl -u admin@izysafe.local:PASSWORD -X POST http://localhost:8082/api/commands \
  -H 'Content-Type: application/json' \
  -d '{"deviceId":<ID>,"type":"custom","attributes":{"data":"CALLBACK,<PARENT_PHONE>#"}}'
```
Common per-vendor variants to try if the above are ignored (record which works):
```
MONITOR,<phone>#        DWXX,<phone>#        LISTEN,<phone>#       # sound around
CALL,<phone>#           DIAL,<phone>#        CALLBACK,<phone>#     # two-way call
```
> Some GT06 watches also accept these directly via **SMS to the watch SIM** (same strings,
> prefixed with the `pw,123456,` password form). If the Traccar command path fails but SMS works,
> that's a finding — note it; it changes how Sprint 7 triggers audio.

### ✅ Success criteria for Step 4
- **Sound Around:** parent phone rings/connects and you hear ambient audio from the watch mic;
  the watch shows its mic-active indicator (consent requirement, CLAUDE.md §3.13).
- **Two-way Call:** parent and child can talk duplex.
- You have **recorded the exact working command string per watch model** → feeds Sprint 7.

---

## 5. What about the `locations` table?

> **Important scope note.** Our app's `locations` table is **not** filled by Traccar directly.
> It is populated by the **backend webhook handler** (`POST /api/v1/webhook/traccar` →
> `location_service.process_update()`), which is built in **Sprint 2**. Traccar is already
> configured to forward positions there (`forward.enable` in `traccar.xml`), but the receiving
> endpoint doesn't exist yet.

So for this Sprint-0 spike:
- **Now:** verify ingestion on the **Traccar side** (`tc_positions`, §3). That proves the watch →
  Traccar leg works end to end.
- **After Sprint 2:** the same watch movement will flow Traccar → webhook → Redis + Firebase +
  the partitioned `locations` table. You'll then confirm with:
  ```bash
  docker exec izysafe-postgres psql -U izysafe -d izysafe -c \
    "SELECT device_id, lat, lng, speed, battery, timestamp \
     FROM locations ORDER BY timestamp DESC LIMIT 5;"
  ```
  Expected: one row per ~30s update, correct lat/lng, `battery` populated, `timestamp` current,
  and the row landing in the right monthly partition (e.g. `locations_2026_06`).

---

## 6. Spike sign-off checklist

- [ ] Traccar admin account created; API reachable.
- [ ] Watch (or simulator) registered by IMEI; shows **online**.
- [ ] `tc_positions` receiving rows with valid coordinates.
- [ ] Working **MONITOR** command string recorded for the model.
- [ ] Working **CALLBACK** command string recorded for the model.
- [ ] Battery field present in GT06 packets (confirms F9 Low-Battery feasibility).
- [ ] Note any watch that needs SMS-based audio instead of Traccar commands (affects Sprint 7).
