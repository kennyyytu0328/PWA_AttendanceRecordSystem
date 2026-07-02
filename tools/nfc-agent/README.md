# NFC door-tap push agent

Pushes the SOYAL 701 `YYYYMM.txt` export to the attendance backend for
per-side gap-fill. See `docs/superpowers/specs/2026-07-01-nfc-punch-backup-design.md`.

## Current deployment (as-built, verified 2026-07-03)

| Item | Value |
|---|---|
| Machine | `DESKTOP-MMGK6PJ` (door PC, office LAN, DHCP — `192.168.2.165` as of 2026-07-03) |
| Install folder | `C:\Users\ltre5\nfc-agent\` |
| Files | `push-nfc.ps1`, `curl.exe`, `curl-ca-bundle.crt` (+ `push-nfc.log`) |
| curl | 8.21.0 win64 from curl.se — LibreSSL 4.3.2 backend, TLS 1.3-capable |
| API key | `NFC_IMPORT_API_KEY` set as a **machine** env var (HKLM) — done |
| Scheduled task | `GoGoFresh NFC Push` — daily **00:20**, `/RU SYSTEM` — registered |
| SOYAL export | `C:\Users\ltre5\OneDrive\桌面\門禁\YYYYMM.txt`, generated daily ~00:10 |

End-to-end verification on 2026-07-03:

- Manual run: `OK 202607.txt: in=0 out=1 skipped=7 unknown=[] terminated=[]`
- Task-Scheduler-triggered run right after: `OK 202607.txt: in=0 out=0 skipped=8 …`
  (the side filled by the first run now counts as "already punched" — confirms
  idempotency), task last-run result `0`.

## Remote management (SSH)

The door PC runs **OpenSSH Server** (OpenSSH for Windows 9.5). Its hostname does
not resolve on the LAN — connect by IP (DHCP; re-check the router lease if
unreachable).

- Interactive: `ssh gogoffcc_doorcontrol` (`~/.ssh/config` alias →
  `gateadmin@192.168.2.165`, password-only auth — the password is deliberately
  **not** written in this repo; ask ICT).
- Scripted (OpenSSH cannot take a password non-interactively): use PuTTY
  `plink` / `pscp` with the **pinned host key**. Without `-hostkey`, plink hangs
  forever on the first-connection registry prompt — even with `echo y |` piped in.

  ```cmd
  plink -batch -ssh -hostkey "SHA256:5do06ov4BYF3zmNRXD0rdbLTJZORSDSwlDD7ZPy8ZZs" ^
    -pw <password> gateadmin@192.168.2.165 "schtasks /Query /TN ""GoGoFresh NFC Push"""

  pscp -batch -hostkey "SHA256:5do06ov4BYF3zmNRXD0rdbLTJZORSDSwlDD7ZPy8ZZs" ^
    -pw <password> push-nfc.ps1 gateadmin@192.168.2.165:C:/Users/ltre5/nfc-agent/
  ```

  The remote shell is `cmd.exe`; wrap PowerShell as
  `powershell -NoProfile -Command "..."`. The `gateadmin` account can read/write
  `C:\Users\ltre5\` and manage scheduled tasks.

## Install / reinstall on the door PC

1. Copy `push-nfc.ps1` to `C:\Users\ltre5\nfc-agent\push-nfc.ps1` (the deployed
   path — if you relocate it, update the scheduled task's `/TR` path to match).
2. Download **curl for Windows** (64-bit) from <https://curl.se/windows/> and
   copy `bin\curl.exe` **and** `bin\curl-ca-bundle.crt` from the zip into the
   same folder as the script.

   > Why: the production edge accepts **TLS 1.3 only**, and Windows 10's
   > built-in TLS stack (used by `Invoke-RestMethod` and
   > `System32\curl.exe`) tops out at TLS 1.2. The curl.se build carries its
   > own TLS library (LibreSSL as of 8.21.0) that speaks TLS 1.3. The script
   > exits with a clear log error if `curl.exe` is missing.

3. Set the API key as a machine environment variable (matches backend
   `NFC_IMPORT_API_KEY`) — run from an **elevated** prompt, then reboot (or
   restart the Task Scheduler service) so scheduled tasks see it.
   *(Already set on the current install.)*

   ```powershell
   [Environment]::SetEnvironmentVariable("NFC_IMPORT_API_KEY", "<the-secret>", "Machine")
   ```

4. Register the daily scheduled task (runs 00:20, after the 00:10 export):

   ```cmd
   schtasks /Create /SC DAILY /ST 00:20 /RU SYSTEM /TN "GoGoFresh NFC Push" ^
     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\ltre5\nfc-agent\push-nfc.ps1"
   ```

   `/RU SYSTEM` runs the task regardless of who (if anyone) is logged in.
   *(Already registered on the current install.)*

## Verify

- Run once by hand (or `schtasks /Run /TN "GoGoFresh NFC Push"`) and check the log:

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\ltre5\nfc-agent\push-nfc.ps1
  Get-Content C:\Users\ltre5\nfc-agent\push-nfc.log -Tail 5
  ```

- Expect a line like `OK 202607.txt: in=0 out=1 skipped=7 unknown=[] terminated=[]`.
- End-to-end: tap test card `02400:09483`, wait for the next export, run the
  script, then confirm the punch appears on that employee's day in the app.

## Notes

- Params can be overridden, e.g. `push-nfc.ps1 -Folder "D:\door" -ApiUrl "https://…/api/nfc/import" -CurlExe "D:\tools\curl.exe"`.
- The door PC's DHCP IP is irrelevant to the push — this only makes outbound calls.
  (It matters only for SSHing in, see above.)
- Sends the file bytes raw (CP950) via `curl --data-binary`; the backend does the decoding.
- The script is saved as UTF-8 **with BOM** — required for the Chinese folder
  path to survive Windows PowerShell 5.1. Keep the BOM if you edit it.
- If you edit `push-nfc.ps1`, redeploy it with `pscp` (see Remote management)
  and compare hashes: `certutil -hashfile C:\Users\ltre5\nfc-agent\push-nfc.ps1 SHA256`
  on the door PC vs `Get-FileHash` locally.
