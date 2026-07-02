# NFC door-tap push agent

Pushes the SOYAL 701 `YYYYMM.txt` export to the attendance backend for
per-side gap-fill. See `docs/superpowers/specs/2026-07-01-nfc-punch-backup-design.md`.

## Install on the door PC (`DESKTOP-MMGK6PJ`)

1. Copy `push-nfc.ps1` to e.g. `C:\nfc-agent\push-nfc.ps1`.
2. Download **curl for Windows** (64-bit) from <https://curl.se/windows/> and
   copy `bin\curl.exe` **and** `bin\curl-ca-bundle.crt` from the zip into the
   same folder as the script.

   > Why: the production edge accepts **TLS 1.3 only**, and Windows 10's
   > built-in TLS stack (used by `Invoke-RestMethod` and
   > `System32\curl.exe`) tops out at TLS 1.2. The OpenSSL-based curl build
   > provides TLS 1.3. The script exits with a clear log error if
   > `curl.exe` is missing.

3. Set the API key as a machine environment variable (matches backend
   `NFC_IMPORT_API_KEY`) — run from an **elevated** prompt, then reboot (or
   restart the Task Scheduler service) so scheduled tasks see it:

   ```powershell
   [Environment]::SetEnvironmentVariable("NFC_IMPORT_API_KEY", "<the-secret>", "Machine")
   ```

4. Register the daily scheduled task (runs 00:20, after the 00:10 export):

   ```cmd
   schtasks /Create /SC DAILY /ST 00:20 /RU SYSTEM /TN "GoGoFresh NFC Push" ^
     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\nfc-agent\push-nfc.ps1"
   ```

   `/RU SYSTEM` runs the task regardless of who (if anyone) is logged in.

## Verify

- Run once by hand and check the log:

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File C:\nfc-agent\push-nfc.ps1
  Get-Content C:\nfc-agent\push-nfc.log -Tail 5
  ```

- Expect a line like `OK 202607.txt: in=3 out=1 skipped=10 unknown=[] terminated=[]`.
- End-to-end: tap test card `02400:09483`, wait for the next export, run the
  script, then confirm the punch appears on that employee's day in the app.

## Notes

- Params can be overridden, e.g. `push-nfc.ps1 -Folder "D:\door" -ApiUrl "https://…/api/nfc/import" -CurlExe "D:\tools\curl.exe"`.
- The door PC's DHCP IP is irrelevant — this only makes outbound calls.
- Sends the file bytes raw (CP950) via `curl --data-binary`; the backend does the decoding.
- The script is saved as UTF-8 **with BOM** — required for the Chinese folder
  path to survive Windows PowerShell 5.1. Keep the BOM if you edit it.
