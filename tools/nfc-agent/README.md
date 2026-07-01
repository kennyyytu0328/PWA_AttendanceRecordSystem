# NFC door-tap push agent

Pushes the SOYAL 701 `YYYYMM.txt` export to the attendance backend for
per-side gap-fill. See `docs/superpowers/specs/2026-07-01-nfc-punch-backup-design.md`.

## Install on the door PC (`DESKTOP-MMGK6PJ`)

1. Copy `push-nfc.ps1` to e.g. `C:\nfc-agent\push-nfc.ps1`.
2. Set the API key as a machine environment variable (matches backend
   `NFC_IMPORT_API_KEY`):

   ```powershell
   [Environment]::SetEnvironmentVariable("NFC_IMPORT_API_KEY", "<the-secret>", "Machine")
   ```

3. Register the daily scheduled task (runs 00:20, after the 00:10 export):

   ```cmd
   schtasks /Create /SC DAILY /ST 00:20 /RL HIGHEST /TN "GoGoFresh NFC Push" ^
     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\nfc-agent\push-nfc.ps1"
   ```

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

- Params can be overridden, e.g. `push-nfc.ps1 -Folder "D:\door" -ApiUrl "https://…/api/nfc/import"`.
- The door PC's DHCP IP is irrelevant — this only makes outbound calls.
- Sends the file bytes raw (CP950); the backend does the decoding.
