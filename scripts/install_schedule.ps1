# Registers two per-user scheduled tasks (no admin needed). Settings: scripts\crew.config.ps1.
#   <ProjectName>-DailyCrew  the crew shift: daily at $RunTime, plus a catch-up trigger
#                            $LogonDelayMinutes after each logon (daily_crew.ps1 decides whether
#                            that catch-up actually runs; see the header of that script).
#   <ProjectName>-HQ         starts the HQ dashboard (http://127.0.0.1:$HqPort) at logon.
# Re-run after editing crew.config.ps1; -Force replaces the existing tasks.
# Remove with scripts\uninstall_schedule.ps1.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'crew.config.ps1')
$root = Split-Path -Parent $PSScriptRoot
$user = "$env:USERDOMAIN\$env:USERNAME"
New-Item -ItemType Directory -Force (Join-Path $root 'output\logs') | Out-Null

if (-not (Test-Path (Join-Path $root '.venv\Scripts\python.exe'))) {
    Write-Warning "No .venv yet: run 'python -m venv .venv' and '.venv\Scripts\pip install -r requirements.txt' first."
}

$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

# --- the crew shift
# StartWhenAvailable: if the machine was off/asleep at RunTime, run as soon as it's back.
# IgnoreNew: the logon catch-up and the daily trigger never run two shifts at once.
$crewArgs = @{
    StartWhenAvailable         = $true
    DontStopIfGoingOnBatteries = $true
    AllowStartIfOnBatteries    = $true
    ExecutionTimeLimit         = (New-TimeSpan -Hours $ShiftHours)
    MultipleInstances          = 'IgnoreNew'
}
if ($WakeToRun) { $crewArgs.WakeToRun = $true }
$crewSettings = New-ScheduledTaskSettingsSet @crewArgs

$daily = New-ScheduledTaskTrigger -Daily -At $RunTime
# Store the start as plain local time (no UTC offset), so the shift follows the wall clock
# across daylight-saving changes instead of drifting an hour.
$daily.StartBoundary = ([datetime]::Today.Add([TimeSpan]$RunTime)).ToString('yyyy-MM-ddTHH:mm:ss')
$logonCatchUp = New-ScheduledTaskTrigger -AtLogOn -User $user
$logonCatchUp.Delay = "PT$($LogonDelayMinutes)M"
$crew = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $root `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$root\scripts\daily_crew.ps1`""
Register-ScheduledTask -TaskName "$ProjectName-DailyCrew" -Action $crew -Trigger @($daily, $logonCatchUp) `
    -Settings $crewSettings -Principal $principal -Force | Out-Null

# --- the dashboard
# pythonw has no stdout, which crashes uvicorn's logging; run python.exe in a hidden PowerShell instead.
$hqSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Days 30) -MultipleInstances IgnoreNew
$hqCmd = "& '$root\.venv\Scripts\python.exe' -m uvicorn dashboard.app:app --host 127.0.0.1 --port $HqPort *>> '$root\output\logs\hq.log'"
$hq = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $root `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command `"$hqCmd`""
Register-ScheduledTask -TaskName "$ProjectName-HQ" -Action $hq `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $user) -Settings $hqSettings -Principal $principal -Force | Out-Null

Get-ScheduledTask -TaskName "$ProjectName-*" | Select-Object TaskName, State
Write-Output "Daily shift at $RunTime (+ catch-up $LogonDelayMinutes min after logon). Dashboard: http://127.0.0.1:$HqPort"
Write-Output "Test the decision logic now with: powershell -File scripts\daily_crew.ps1 -DryRun"
