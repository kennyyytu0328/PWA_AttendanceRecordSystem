# NFC Door-Tap Gap-Fill Backup — Design & Integration Reference

- **Date:** 2026-07-01
- **Branch:** `feature/nfc-punch-backup`
- **Status:** Approved design (pre-implementation)
- **Author:** Kenny Tu (with Claude)

This document is both the **design spec** for the feature and the permanent
**integration reference** for the external NFC door-control system. Keep it up to
date as deployment parameters are confirmed.

---

## 1. Summary & Goal

NFC card taps at either office door act as a **backup source of punch times**. If an
employee forgot (or was unable) to punch on the phone/WebAuthn PWA but physically
tapped their card at a door, the tap **fills the missing punch**. If the employee
already punched on the phone, the phone record **wins** — NFC never competes.

The fill is **per-side**: it fills only whichever of 上班 (clock-in) / 下班
(clock-out) is missing. This is a *gap-fill*, not a merge.

Everything the system already does (WebAuthn PWA punch, geolocation, monthly
override, reports, Taiwan calendar, etc.) is **unchanged**. This feature only adds a
new, isolated backup import path.

---

## 2. The external door-control system (facts to record)

| Item | Value |
|------|-------|
| Door-control software | **SOYAL 701 Client/Server** (Taiwanese access-control system) |
| Door-PC hostname | `DESKTOP-MMGK6PJ` |
| Windows user | `ltre5` |
| File folder | `C:\Users\ltre5\OneDrive\桌面\門禁\` |
| File name pattern | `YYYYMM.txt` (e.g. `202607.txt`) — **one file per month, cumulative** |
| File generated | ~**00:10 every day** (the door system writes/refreshes the month file) |
| Encoding | **CP950 / Big5** (Traditional Chinese) |
| Offices / doors | **2 offices**, each door has its own door number (`1`, `2`) |
| Door-PC LAN IP | `192.168.2.165` (Wi-Fi) — **DHCP dynamic, may change** — on the `192.168.2.0/24` office LAN |
| Network | Door PC sits on the **office LAN** (private IP behind NAT). Prod (`go2fresh-1`) is **remote** relative to that LAN. |

**Deployment notes (confirmed 2026-07-01):**
- The door PC's IP is **DHCP-assigned and may change** — which is exactly why the
  push-agent design does not depend on it. The door PC only needs outbound internet to
  reach prod; its own address is irrelevant. (It sits on `192.168.2.0/24`, the same
  subnet the dev config whitelists via `allowedDevOrigins: 192.168.2.*`, so a door PC →
  dev-machine push can be tested locally on the LAN.)
- `card_serial` (field 5) is the **card UID** read from the physical NFC card
  (informational only; the import does not use it). The printed 站碼:卡號 format is the
  same 10-digit serial with a colon between the 5-digit site code and 5-digit card
  number — i.e. printed `02400:09483` = in-file `card_serial` `0240009483`.
- **Join key confirmed:** field 3 in the real SOYAL export is natively our `emp_id`
  (e.g. `F1000118`) — SOYAL 701's user-number is set to the emp_id — so **no mapping
  layer is needed**. Test card UID **`02400:09483`** is registered to a real employee
  for end-to-end verification.

---

## 3. `YYYYMM.txt` format specification

Comma-separated, one tap per line, no header:

```
date, time, emp_id, door_no, card_serial, name
```

| # | Field | Example | Format | Used? |
|---|-------|---------|--------|-------|
| 1 | date | `20260701` | `YYYYMMDD` | ✅ |
| 2 | time | `072437` | `HHMMSS` (24h) | ✅ |
| 3 | emp_id | `F1000118` | matches `employees.emp_id` | ✅ (join key) |
| 4 | door_no | `1` / `2` | office/door number | ℹ️ logged only |
| 5 | card_serial | `5717003342` | physical **card UID** (as read by SOYAL) | ℹ️ logged only |
| 6 | name | `王小明` | employee name, **CP950** | ℹ️ logged only |

Sample raw lines (names appear as mojibake when the file is read as UTF-8 — this is
the tell-tale sign the file is CP950 and must be decoded with `encoding="cp950"`):

```
20260701,072437,F1000118,1,5717003342,<CP950 name bytes>
20260701,074042,F1000818,1,5716344222,<CP950 name bytes>
20260701,081045,F1000220,2,6108331019,<CP950 name bytes>
```

**Important:** `door_no` is **NOT** in/out direction. It identifies which of the two
offices the tap happened at. In/out is therefore inferred by **time**, not by this
field (see §5).

---

## 4. Integration architecture — how the two sides connect

### The constraint
The door PC has a **private LAN IP behind NAT**. Prod (`go2fresh-1`) is remote.
Inbound internet → private LAN is blocked; **outbound LAN → internet is allowed**.
Therefore "prod pulls from the door PC" is the hard/blocked direction.

### The chosen pattern — **push agent**
The **LAN side pushes** the file out to prod's existing public HTTPS endpoint. No
VPN, port-forwarding, or firewall changes required.

```
Door PC (office LAN)                         Prod (go2fresh-1, Docker)
──────────────────────                       ──────────────────────────
00:10  door system writes YYYYMM.txt
00:20  Task Scheduler runs push-nfc.ps1:     POST /api/nfc/import
         read YYYYMM.txt as raw bytes  ─────► (X-NFC-API-Key, HTTPS)
         POST to prod API                       │ decode cp950
                                                 │ parse rows
                                                 │ per-side gap-fill (idempotent)
                                                 │ regenerate daily summaries
                                                 └─► JSON report ──► logged by script
```

All parsing / decoding / gap-fill / summary logic lives in the **backend** (version
controlled, testable). The door-side script is intentionally dumb: read file → POST.

**Alternatives considered & rejected for v1:** OneDrive/Microsoft-Graph cloud pull
(needs Azure app + OAuth upkeep); VPN/tunnel e.g. Tailscale (persistent infra to
maintain for one small daily file). Both remain clean future options.

---

## 5. In/out inference (time-based)

Per `(emp_id, date)`, over that day's NFC taps (across both doors):
- **earliest tap → clock-in candidate**
- **latest tap → clock-out candidate**

`door_no` is ignored for the logic. An employee may tap Office 1 in the morning and
Office 2 at night — time still resolves in/out correctly. This mirrors the system's
existing **First-In-Last-Out** model.

---

## 6. Per-side gap-fill algorithm (core)

For each `(emp_id, date)` present in the file:

| Existing **real** punches that day | Action |
|---|---|
| 0 (whole day empty) | Insert NFC clock-in (earliest tap). If ≥2 taps, also insert NFC clock-out (latest tap). |
| 1 (has clock-in, missing clock-out) | Insert **only** NFC clock-out (latest tap), *if later than the existing clock-in*. |
| 2+ (complete) | Do nothing — phone wins. |

Rules:
- **"Existing punches"** = non-overridden `attendance_logs` for that day (phone
  punches **and** prior NFC-filled logs both count).
- Insert **at most one in-log and one out-log**, only for the missing side, so NFC
  can **never displace** a real phone punch.
- **Clock-out time guard:** the clock-out candidate is used only if it is *strictly
  later* than the effective clock-in. Prevents clock-out-before-clock-in and stops a
  single tap from fabricating a clock-out.
- **Min work-duration guard:** **OFF for v1** (decided). (Future tunable: only fill
  the out-side when `latest − earliest ≥ N` minutes, to reduce false EARLY_LEAVE.)

**Known limitation (accepted):** with only door timestamps, if someone taps twice in
the morning and never taps when leaving, the latest morning tap becomes a same-day
"clock-out" (would show EARLY_LEAVE). This is inherent to door data. The employee
corrects it via the existing **Monthly Punch Override** — same safety valve as today.

---

## 7. Idempotency (safe re-import)

The month file is re-sent daily with growing content. Because "existing punches"
includes prior NFC-filled logs, an already-filled side is skipped on re-run. Inserts
are additionally deduped on `emp_id + exact timestamp`. **Running the import N times
= same result as running it once.** Manual/HR overrides always win (override marks
prior logs `is_overridden=True`; NFC then sees the override logs as the existing
punches and skips).

---

## 8. Backend design

Follows the project's layered pattern (router → service → repository; no direct DB in
routers; async; type-hinted; immutable result types).

- **Router** `backend/app/routers/nfc.py`
  - `POST /api/nfc/import` — accepts the raw file body (CP950 bytes). Auth via API
    key (§9). Returns the import report (§10).
- **Service** `backend/app/services/nfc_import_service.py`
  - decode cp950 → parse rows → group by `(emp_id, date)` → apply §6 → regenerate
    daily summaries with the calendar-accurate `day_kind` (reuse
    `reporting_service.generate_daily_summary`) → build report.
- **Repository** — reuse `attendance_repository` (`create_log`,
  `find_by_employee_and_date`) and `summary_repository`. Add a small helper only if
  needed for the exact-timestamp NFC dedup.
- **Source marker on inserted logs:** `ip_address="nfc"`, `work_mode=OFFICE`,
  `latitude=longitude=accuracy=0`, `is_overridden=False`. Reuses the existing
  convention (`ip_address="override"` for bulk overrides). *(Alternative — a proper
  `source` column — deferred to avoid a migration on a core table; easy to promote
  later.)*

---

## 9. Security

- Endpoint authenticated by an **API key** in header `X-NFC-API-Key`, compared to env
  var **`NFC_IMPORT_API_KEY`** (added to `backend/.env.example` and
  `backend/.env.production.example`; **never hardcoded**; real value only in prod
  `.env` and the door-PC scheduled task).
- HTTPS only. Reuse existing rate limiting. Machine-to-machine — **not** JWT (the door
  script is not a logged-in user).
- Invalid/missing key → `401`. Unknown `emp_id`s are skipped, not fatal (no user
  enumeration concern — this is an internal trusted feed).

---

## 10. Report / observability

`POST /api/nfc/import` returns JSON:

```json
{
  "filled_in": 0,
  "filled_out": 0,
  "skipped_already_punched": 0,
  "skipped_already_imported": 0,
  "unknown_emp_ids": [],
  "parse_errors": [],
  "affected_days": []
}
```

The door script logs this line-by-line locally. *(A persisted `nfc_import_runs` audit
table is a v2 nice-to-have.)*

---

## 11. Door-side push script

- **`tools/nfc-agent/push-nfc.ps1`** (PowerShell — zero install on Windows) + a short
  **README** covering: registering the Task Scheduler job, where to store the API key,
  and the prod endpoint URL.
- Behavior: compute the current-month filename → read `YYYYMM.txt` as **raw bytes**
  (no client-side decode) → POST to prod with `X-NFC-API-Key`. On the **1st of the
  month**, also send **last month's** file (to catch the final day's late taps).
  Retry on network failure; append a local log line.
- Schedule: **daily ~00:20** (after the 00:10 file generation).

---

## 12. Weekend / holiday handling

Taps are recorded for **every day** in the file (decided: record all taps, including
Sundays). Summary regeneration uses the Taiwan-calendar `day_kind`, so weekend/holiday
work is scored **NORMAL** (never LATE/EARLY_LEAVE), consistent with existing rules
(#31f). The human-facing Sunday "例假日" write-lock is intentionally **not** replicated
here — NFC records factual hardware evidence.

---

## 13. Edge cases

- **Unknown emp_id** (in file, not in `employees`) → skip, add to
  `unknown_emp_ids`. Never fails the batch.
- **Terminated employee** → skip gap-fill, note in report.
- **Malformed / short row / bad date-time** → skip, collect in `parse_errors`.
- **Month rollover** → handled by the 1st-of-month dual-send (§11).
- **Empty or missing file** → script logs and exits 0 (no-op); endpoint handles empty
  body gracefully.

---

## 14. Testing (TDD, 80%+ target)

**Backend unit tests** (`nfc_import_service`):
- CP950 decode of a Big5 fixture (names round-trip correctly).
- Row parsing incl. malformed rows → `parse_errors`.
- Gap-fill §6: whole-day-empty (2 taps → in+out; 1 tap → in only), in-only day
  (fills out), complete day (no-op).
- Clock-out time guard (latest ≤ clock-in → no out inserted).
- Idempotent re-import (second run inserts nothing).
- Unknown emp_id and terminated emp_id handling.
- Summary regeneration produces correct status incl. weekend = NORMAL.

**Integration test** (`POST /api/nfc/import`):
- Valid key + sample CP950 file → expected report + logs created.
- Missing/invalid key → `401`.

---

## 15. Configuration & environment

- New env var `NFC_IMPORT_API_KEY` (backend) — add to `.env.example` and
  `.env.production.example`.
- No CORS impact (called by a script, not a browser).
- No DB migration in v1 (source marker reuses `ip_address`).

---

## 16. Out of scope for v1

OneDrive/Graph pull · VPN/tunnel · `source` column migration · `nfc_import_runs` audit
table · admin UI for browsing imports. All are additive later.

---

## 17. Open questions / v2 ideas

- Persisted import-run audit table + a small HR view.
- Promote `ip_address="nfc"` to a first-class `source` enum column.
- Optional min work-duration guard (§6) if false EARLY_LEAVE proves noisy.
- Second daily push (e.g. midday) if same-day visibility is wanted.
