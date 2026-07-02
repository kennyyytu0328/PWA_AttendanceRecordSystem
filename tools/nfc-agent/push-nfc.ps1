# push-nfc.ps1 — read the current-month SOYAL 701 export and POST it to the
# GoGoFresh attendance backend for NFC gap-fill backup.
#
# Runs daily via Task Scheduler (~00:20, after the 00:10 file generation).
# Outbound HTTPS only; needs no inbound/firewall changes on the office LAN.

param(
    [string]$Folder  = "C:\Users\ltre5\OneDrive\桌面\門禁",
    [string]$ApiUrl  = "https://www.gogoffcc.com/gogoffcc-arms/api/nfc/import",
    [string]$ApiKey  = $env:NFC_IMPORT_API_KEY,
    [string]$LogFile = "$PSScriptRoot\push-nfc.log",
    [string]$CurlExe = "$PSScriptRoot\curl.exe"
)

function Write-Log([string]$msg) {
    Add-Content -Path $LogFile -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}

if (-not $ApiKey) {
    Write-Log "ERROR: NFC_IMPORT_API_KEY not set"
    exit 1
}

# The production edge requires TLS 1.3, which Windows 10's schannel stack
# (Invoke-RestMethod and the built-in curl) cannot speak. Ship the OpenSSL
# build of curl from https://curl.se/windows/ next to this script, together
# with its curl-ca-bundle.crt (see README).
if (-not (Test-Path $CurlExe)) {
    Write-Log "ERROR: curl.exe not found at $CurlExe - download from https://curl.se/windows/ (see README)"
    exit 1
}

function Send-File([string]$fileName) {
    $path = Join-Path $Folder $fileName
    if (-not (Test-Path $path)) {
        Write-Log "SKIP: $fileName not found"
        return
    }
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        # --data-binary "@file" posts the raw CP950 bytes untouched.
        $raw = & $CurlExe -sS --fail-with-body -X POST $ApiUrl `
            -H "X-NFC-API-Key: $ApiKey" -H "Content-Type: application/octet-stream" `
            --data-binary "@$path" --max-time 60 2>&1
        $text = ($raw | ForEach-Object { "$_" }) -join " "
        if ($LASTEXITCODE -eq 0) {
            try { $resp = $text | ConvertFrom-Json } catch { $resp = $null }
            if ($resp) {
                Write-Log ("OK {0}: in={1} out={2} skipped={3} unknown=[{4}] terminated=[{5}]" -f `
                    $fileName, $resp.filled_in, $resp.filled_out, $resp.skipped_already_punched, `
                    ($resp.unknown_emp_ids -join "|"), ($resp.skipped_terminated -join "|"))
            } else {
                Write-Log ("OK {0}: unparseable response: {1}" -f $fileName, $text)
            }
            return
        }
        Write-Log ("ERROR {0} attempt {1} (curl exit {2}): {3}" -f $fileName, $attempt, $LASTEXITCODE, $text)
        Start-Sleep -Seconds (5 * $attempt)
    }
    Write-Log "GIVE UP: $fileName after 3 attempts"
}

$now = Get-Date
Send-File ("{0:yyyyMM}.txt" -f $now)
# On the 1st, also resend last month's file to catch the final day's late taps.
if ($now.Day -eq 1) {
    Send-File ("{0:yyyyMM}.txt" -f $now.AddMonths(-1))
}
