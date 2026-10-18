# IzySafe / izyLrn — Admin Operations Guide

How to register parents, students, drivers and buses, attach tracking devices, and view live
location — for both the **School Admin** and the **Parent**.

> Dev URLs used in this guide:
> - Admin panel: `http://localhost:5173`
> - Parent app (web build): `http://localhost:8090`
> - Backend API / Swagger: `http://localhost:8000/docs`
> - Traccar (GPS middleware): `http://localhost:8082`
>
> Dev logins: Admin `panel-demo@school.test` / `demopass123` · Traccar `admin@izysafe.local` / `change_me_traccar_admin` · Parent = phone + OTP (OTP is printed in the backend logs in dev).

---

## 0. The ownership model (read this first — it explains "who adds what")

IzySafe is **two products sharing one backend**:

| Thing | Who owns / creates it | Where |
|---|---|---|
| **Parent account** | The parent themselves (self sign-up) | Parent app (phone + OTP) |
| **Child (student)** | The **parent** | Parent app |
| **Child's tracking device** (watch / phone / tag) | The **parent** (pairs it) | Parent app — auto-registers in Traccar |
| **Enrollment** (links an existing child to a school) | **School admin** | Admin panel → Roster |
| **Consent** (lets the school see the child) | The **parent** approves | Parent app |
| **Driver** | School admin | Admin panel → Drivers |
| **Bus + bus device** | School admin | Admin panel → Routes & Buses |
| **Bus route & stops** | School admin | Admin panel → Routes & Buses |

**Key consequence:** a **child's** device is added by the **parent**, not the admin. The admin panel
has **no** screen to add a device to a student (by design — the child and its tracker belong to the
parent's account). The admin only *views* a student's device/location once the parent has (a) added
the child, (b) paired a device, and (c) approved the school's enrollment with location consent.
Only **bus** devices are added by the admin. *(If you want an admin-managed "add device for a
student" feature, that is new development — see §9.)*

---

## 1. One-time school setup (timezone & school hours)

Admin panel → **Settings** (must be signed in as role = **admin**).

- **Timezone** — *School Profile* card → **Timezone** dropdown → choose **Asia/Dubai** (UAE) → Save.
  This controls how times are shown on the Attendance page. (Default was `Asia/Kolkata`/IST — that is
  why you saw IST.)
- **School hours** — *Attendance / School hours* card → set **Arrival window opens**, **On-time before**,
  **Late until**, **School day ends** (time pickers) → Save.

**Important limitation:** the **days of the week** a school operates (`school_days`) is **not** editable
in the UI yet — it defaults to **Mon–Fri** and can only be changed in the database. Live Tracking shows a
student's position **only during school hours on school days**; outside that window it shows
*"Live location paused (outside school hours)."*

> To make tracking visible **all day, every day** for testing, set the daily window to `00:00`–`23:59`
> in Settings, and (DB-only) set `school_days` to all 7 days:
> ```bash
> docker compose exec -T postgres psql -U izysafe -d izysafe \
>   -c "UPDATE schools SET school_days='{1,2,3,4,5,6,7}' WHERE name='Panel Demo School';"
> ```

---

## 2. Register a PARENT

Parents self-register in the **parent app** (there is no admin screen for this):

1. Open the parent app (`http://localhost:8090` on web, or the mobile build).
2. Enter phone — **+91**XXXXXXXXXX (India) or **+971**XXXXXXXXX (UAE) → **Send code**.
3. Get the OTP:
   - Production: WhatsApp → SMS.
   - **Dev (no SMS gateway): the OTP is printed in the backend logs.** Read it with:
     ```powershell
     docker compose -f C:/Fahad/IzylrnTracker/izysafe/docker-compose.yml logs backend --tail 20 | Select-String "DEV OTP"
     ```
4. Enter the 6-digit code → account is created + logged in (first verify = registration).

---

## 3. Parent adds a CHILD (student)

In the parent app: **Home → Add child** → name (e.g. "Ahmed"), optional class/grade → Save.
The parent becomes the child's **primary parent**.

*(This must happen before the school can enroll the student — see §4.)*

---

## 4. Parent pairs a DEVICE to the child

Still in the parent app: open the child → **Devices → Pair device**:

- **Name** (e.g. "Ahmed's Watch")
- **IMEI** — the tracker's IMEI, **or**, if using a phone as a test tracker, the **Device identifier**
  you set in the Traccar Client app (e.g. `32301379`). These two must match **exactly**.

Pairing **automatically registers the device in Traccar** and links it: `izysafe device.traccar_id`
↔ Traccar device `uniqueId` ↔ child. No manual Traccar step is needed for child devices.

> Using a phone as the tracker: install **Traccar Client**, set **Server URL** `http://<PC-LAN-IP>:5055`
> (e.g. `http://192.168.1.118:5055`), set **Device identifier** = the IMEI you paired, enable
> **Service status**, and grant **Location = Allow all the time**.

---

## 5. School admin ENROLLS the student

Admin panel → **Roster → Add student**:

- **Parent phone** (the number the parent registered with)
- **Student name** (required if the parent has more than one child)
- Class/grade (optional)

Requirements (else you get an error):
- The **parent must already exist** → else *"No parent account for this number"* (`PARENT_NOT_FOUND`).
- The parent must **already have that child** → else *"No matching student for this parent"*
  (`CHILD_NOT_FOUND`). ← this is the error you hit when the child hadn't been created yet.

The enrollment starts as **Pending** (no consent yet).

---

## 6. Parent APPROVES consent (so the school can see the child)

In the parent app the parent sees the pending enrollment and approves it, turning ON:
- **parent_opt_in** — lets the school see the child at all.
- **location_opt_in** — lets the school see the child's **live location**.
- **bus_opt_in** — (optional) for bus tracking/alerts.

**Both `parent_opt_in` and `location_opt_in` must be ON** for a student to show a live position on the
admin Live Tracking page. The parent can withdraw any of these at any time.

---

## 7. Register a DRIVER and a BUS (school-side devices)

### 7a. Driver — Admin panel → **Drivers → Add driver**
- **Name** (required), **Phone** (optional), **Access code** (optional; use **Generate** for a 6-digit code).
- The driver logs into the **separate driver app** with **phone + access code**.
- The code is write-only — it is never shown again (only a "code is set" indicator). **Share it with the
  driver securely.** You can reset it later via **Set/Reset access code**.

### 7b. Bus — Admin panel → **Routes & Buses → Register bus**
- **Name** (required), **IMEI** (required), **Traccar ID** (optional, numeric).
- ⚠️ **Unlike child devices, registering a bus does NOT auto-create the device in Traccar.** You must:
  1. In **Traccar** (`http://localhost:8082`, login above) → **+ (Add device)** → set **Identifier** =
     the bus IMEI → Save. Note the numeric **device id** Traccar assigns.
  2. Back in the admin **Register bus** dialog, paste that number into **Traccar ID**.
  - If **Traccar ID** is left blank, the bus has no live position.

### 7c. Route — Admin panel → **Routes & Buses → create route**
- Create a route (optionally link a **driver** and a **bus device**), add **stops**, and assign
  enrolled **students** to stops.

---

## 8. Viewing live location

### 8a. Admin — **Live Tracking** page (`/tracking`)
- **Everyone (default):** the **Students** and **Buses** tabs list all entities; all markers are shown on
  the map.
- **One individual:** click a student/bus row **or** its map marker → the map flies/zooms to it and a
  **detail panel** opens below (class, device, battery, last-seen; for buses: route, driver, trip, assigned
  students). Selecting another switches focus.
- **Layer toggles** hide/show all buses or all students as a group.
- Data auto-refreshes every ~10 seconds.
- A student appears here only if: enrolled + `parent_opt_in` + `location_opt_in` ON, and a live position
  shows only **during school hours** with a device actively reporting.

### 8b. Parent — parent app
- Open the child → **Live Map** — the parent sees **their own child's** live location, geofences, SOS, etc.
- Parents do not see other families' children; the school sees a child only via opt-in.

### 8c. Driver / bus
- The **driver app** shows the driver's own active trip.
- The **admin** sees the bus on the Buses tab (needs the bus `traccar_id` + the device reporting).
- Parents of students assigned to that bus see **bus ETA / tracking** (with `bus_opt_in`).

---

## 9. Do admins register the phone/device in Traccar manually?

- **Child/student device → NO.** The parent pairs it in the app and it is auto-registered in Traccar.
  There is no admin screen for student devices (ownership model, §0).
- **Bus device → PARTLY YES.** The admin adds the bus (Name + IMEI) in the panel, but must **manually
  create the device in Traccar and paste the numeric Traccar ID** (§7b). This is the one place manual
  Traccar work is required today.

*(Possible enhancement: add an admin "register/pair device for a student" screen and make bus
registration auto-create the Traccar device — both are new development, not current behaviour.)*

---

## 10. Troubleshooting

**Phone's live location not updating (Traccar/admin shows old position):**
1. **Network path** — the phone must reach the PC. Open `http://<PC-LAN-IP>:5055` (e.g.
   `http://192.168.1.118:5055`) **in the phone's browser**:
   - Loads/any response → network OK → check the app (below).
   - Times out → phone and PC are not on the same reachable network. Put the phone on the **exact same
     Wi-Fi SSID** as the PC (watch out for separate 2.4 GHz vs 5 GHz networks like "Ahmed" vs "Ahmed-5G"),
     turn off **mobile data** and any **VPN**, and disable **router AP/client isolation**.
2. **App** — Traccar Client: **Service status ON**, **Location = Allow all the time**, exclude from
   **battery optimization**, **Server URL** = `http://<PC-LAN-IP>:5055`, **identifier** = the paired IMEI.
3. **Device registered** — the identifier must exist as a Traccar device (auto for child devices after
   pairing). Unregistered identifier → Traccar returns 400 and drops the fix.
4. **Verify it arrived:**
   ```powershell
   curl -u admin@izysafe.local:change_me_traccar_admin http://localhost:8082/api/devices
   ```
   A fresh `lastUpdate` = the phone is getting through.

**Times shown in the wrong zone (IST instead of GMT+4):** Settings → School Profile → Timezone →
**Asia/Dubai** (§1).

**Live location "paused":** it is outside the school's hours/days (§1).

---

## 11. Credentials quick reference (dev)

| What | URL | Login |
|---|---|---|
| Admin panel | http://localhost:5173 | `panel-demo@school.test` / `demopass123` |
| Parent app | http://localhost:8090 | phone + OTP (from backend logs in dev) |
| Traccar | http://localhost:8082 | `admin@izysafe.local` / `change_me_traccar_admin` |
| Backend API docs | http://localhost:8000/docs | — |

*All dev defaults — change for production.*
