# Hand today's crew shift to an interactive session, so the scheduled run doesn't start a
# second ARCHITECT on top of you. Writes "=== Claimed by interactive session" into today's
# log; daily_crew.ps1 then skips today (and treats today as done when tomorrow checks for a
# missed day).
#
#   powershell -File scripts\claim_day.ps1            claim today
#   powershell -File scripts\claim_day.ps1 -Release   undo: let the scheduled shift run today
param([switch]$Release)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root 'output\logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("daily-{0:yyyy-MM-dd}.log" -f (Get-Date))

if ($Release) {
    if (Test-Path $log) {
        $keep = Get-Content $log -Encoding UTF8 | Where-Object { $_ -notmatch '^\W*=== Claimed by interactive session' }
        Set-Content -Path $log -Value $keep -Encoding UTF8
    }
    Write-Output "released: the scheduled shift may run today"
} else {
    "=== Claimed by interactive session $(Get-Date -Format s) ===" | Out-File -Append -Encoding utf8 $log
    Write-Output "claimed: today's scheduled shift will not run ($log)"
}
