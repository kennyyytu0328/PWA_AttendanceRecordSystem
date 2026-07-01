# push-nfc.ps1 — read the current-month SOYAL 701 export and POST it to the
# GoGoFresh attendance backend for NFC gap-fill backup.
#
# Runs daily via Task Scheduler (~00:20, after the 00:10 file generation).
# Outbound HTTPS only; needs no inbound/firewall changes on the office LAN.

param(
    [string]$Folder  = "C:\Users\ltre5\OneDrive\桌面\門禁",
    [string]$ApiUrl  = "https://www.gogoffcc.com/gogoffcc-arms/api/nfc/import",
    [string]$ApiKey  = $env:NFC_IMPORT_API_KEY,
    [string]$LogFile = "$PSScriptRoot\push-nfc.log"
)

function Write-Log([string]$msg) {
    Add-Content -Path $LogFile -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg)
}

if (-not $ApiKey) {
    Write-Log "ERROR: NFC_IMPORT_API_KEY not set"
    exit 1
}

function Send-File([string]$fileName) {
    $path = Join-Path $Folder $fileName
    if (-not (Test-Path $path)) {
        Write-Log "SKIP: $fileName not found"
        return
    }
    $bytes = [System.IO.File]::ReadAllBytes($path)
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            $resp = Invoke-RestMethod -Uri $ApiUrl -Method Post -Body $bytes `
                -ContentType "application/octet-stream" `
                -Headers @{ "X-NFC-API-Key" = $ApiKey } -TimeoutSec 60
            Write-Log ("OK {0}: in={1} out={2} skipped={3} unknown=[{4}] terminated=[{5}]" -f `
                $fileName, $resp.filled_in, $resp.filled_out, $resp.skipped_already_punched, `
                ($resp.unknown_emp_ids -join "|"), ($resp.skipped_terminated -join "|"))
            return
        } catch {
            Write-Log ("ERROR {0} attempt {1}: {2}" -f $fileName, $attempt, $_.Exception.Message)
            Start-Sleep -Seconds (5 * $attempt)
        }
    }
    Write-Log "GIVE UP: $fileName after 3 attempts"
}

$now = Get-Date
Send-File ("{0:yyyyMM}.txt" -f $now)
# On the 1st, also resend last month's file to catch the final day's late taps.
if ($now.Day -eq 1) {
    Send-File ("{0:yyyyMM}.txt" -f $now.AddMonths(-1))
}
