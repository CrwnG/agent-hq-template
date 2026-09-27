# Unattended daily crew shift. Registered with Windows Task Scheduler by scripts\install_schedule.ps1.
# Settings (project name, run time, turn budget, extra tools) live in scripts\crew.config.ps1.
#
# Runs Claude Code headless on the owner's subscription (never the API) with
# .claude\commands\daily-crew.md as the prompt, in dontAsk mode: anything not on the allowlist
# below is refused rather than prompting (nobody is there to answer). Logs go to
# output\logs\daily-YYYY-MM-DD.log with secrets masked.
#
# Two triggers call this script: daily at $RunTime, and $LogonDelayMinutes after each logon.
#   - today's log has "=== Finished ... exit code 0" or "=== Claimed by interactive session"
#       -> exit: today's shift is done, or an interactive session took it (scripts\claim_day.ps1)
#   - yesterday's shift finished (or was claimed) and it's before RunTime - LogonGraceMinutes
#       -> exit: too early, the daily trigger will run it
#   - otherwise run. So a missed day (machine off all day) catches up at the next logon
#     whatever the time, and a machine that was off at RunTime runs the shift once it's back.
#   - today's shift started but never finished (a shutdown or sleep killed it)
#       -> run again, with a note telling ARCHITECT to resume rather than redo.
#
#   -Force    skip every check and run now
#   -DryRun   print the decision ("run: ..." / "skip: ...") and exit without running anything
param(
    [switch]$Force,
    [switch]$DryRun,
    [string]$LogDir,
    [datetime]$Now = (Get-Date)
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'crew.config.ps1')
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Never bill the API by accident: with ANTHROPIC_API_KEY set, claude -p uses (and bills) the API
# key instead of the logged-in subscription.
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue

if (-not $LogDir) { $LogDir = Join-Path $root 'output\logs' }
New-Item -ItemType Directory -Force $LogDir | Out-Null
$log = Join-Path $LogDir ("daily-{0:yyyy-MM-dd}.log" -f $Now)

# Markers. '^\W*' tolerates the UTF-8 BOM that Windows PowerShell writes at the start of a file.
$P_STARTED  = '^\W*=== Daily crew shift started'
$P_FINISHED = '^\W*=== Finished .* with exit code 0 ==='
$P_CLAIMED  = '^\W*=== Claimed by interactive session'
function Test-Marker([string]$Path, [string]$Pattern) {
    (Test-Path $Path) -and [bool](Select-String -Path $Path -Pattern $Pattern -Quiet)
}

$started  = Test-Marker $log $P_STARTED
$finished = Test-Marker $log $P_FINISHED
$claimed  = Test-Marker $log $P_CLAIMED

# Was the last shift yesterday, and did it finish (or get claimed)? If not, a day was missed.
$prev = Get-ChildItem $LogDir -Filter 'daily-*.log' | Where-Object { $_.Name -lt (Split-Path $log -Leaf) } |
        Sort-Object Name | Select-Object -Last 1
if (-not $prev) {
    $caughtUp = $true   # first ever run: wait for the scheduled time
} else {
    $prevDay = [datetime]::ParseExact($prev.BaseName.Substring(6), 'yyyy-MM-dd', $null)
    $caughtUp = ($prevDay.Date -eq $Now.Date.AddDays(-1)) -and
                ((Test-Marker $prev.FullName $P_FINISHED) -or (Test-Marker $prev.FullName $P_CLAIMED))
}
$earliest = ([TimeSpan]$RunTime).Subtract([TimeSpan]::FromMinutes($LogonGraceMinutes))

$decision = 'run: scheduled shift'
if ($Force) { $decision = 'run: forced' }
elseif ($finished) { $decision = 'skip: today''s shift already finished' }
elseif ($claimed) { $decision = 'skip: claimed by an interactive session' }
elseif ($caughtUp -and $Now.TimeOfDay -lt $earliest) { $decision = "skip: too early, the $RunTime trigger will run it" }
elseif (-not $caughtUp) { $decision = 'run: catching up a missed day' }
if ($started -and -not $finished -and $decision -like 'run*') { $decision += ' (resuming an interrupted shift)' }

if ($DryRun) { Write-Output $decision; exit 0 }
if ($decision -like 'skip*') { exit 0 }

$prompt = (Get-Content (Join-Path $root '.claude\commands\daily-crew.md') -Raw -Encoding UTF8) -replace '(?s)^---.*?---\s*', ''
if ($started -and -not $finished) {
    $prompt = "NOTE: an earlier shift today was interrupted (shutdown or sleep). Check today's HQ events " +
              "(python -m hq.query) and git log first, and skip or finish steps that are already done; " +
              "don't redo them.`n`n" + $prompt
}

# The allowlist. dontAsk mode refuses everything else, so an unattended run can't wander.
$allowed = @(
    'Read', 'Glob', 'Grep', 'Write', 'Edit', 'Agent', 'WebSearch', 'WebFetch',
    'Bash(.venv/Scripts/python.exe -m *)', 'PowerShell(.venv\Scripts\python.exe -m *)',
    'Bash(git status*)', 'Bash(git add *)', 'Bash(git commit *)', 'Bash(git log*)', 'Bash(git diff*)'
) + $ExtraAllowedTools

# Secrets never reach the log: mask every value in .env (except non-secret HQ_* settings)
# plus anything shaped like a common API key or token.
$secretValues = @()
$envFile = Join-Path $root '.env'
if (Test-Path $envFile) {
    $secretValues = @(Get-Content $envFile | Where-Object { $_ -match '^\s*[A-Za-z_][A-Za-z0-9_]*\s*=' -and $_ -notmatch '^\s*HQ_' } |
        ForEach-Object { ($_ -split '=', 2)[1].Trim().Trim('"').Trim("'") } | Where-Object { $_.Length -ge 8 })
}
$secretPatterns = @(
    'sk-ant-[A-Za-z0-9_\-]+', 'sk-[A-Za-z0-9_\-]{20,}', 'gh[pousr]_[A-Za-z0-9]{20,}',
    'github_pat_[A-Za-z0-9_]{20,}', 'xox[abposr]-[A-Za-z0-9\-]{10,}', 'AKIA[0-9A-Z]{16}',
    '(?i)bearer\s+[A-Za-z0-9._\-]{16,}'
)
function Hide-Secrets([string]$Line) {
    foreach ($v in $secretValues) { $Line = $Line.Replace($v, '***REDACTED***') }
    foreach ($p in $secretPatterns) { $Line = $Line -replace $p, '***REDACTED***' }
    $Line
}

$claude = Join-Path $env:APPDATA 'npm\claude.cmd'
if (-not (Test-Path $claude)) {
    $cmd = Get-Command claude -ErrorAction SilentlyContinue
    if ($cmd) { $claude = $cmd.Source }
    else { "=== ERROR $(Get-Date -Format s): claude CLI not found (npm i -g @anthropic-ai/claude-code) ===" | Out-File -Append -Encoding utf8 $log; exit 1 }
}

# The task wakes (or finds) the machine awake, but Windows puts it back to sleep after its idle
# timeout, killing the shift mid-run. Hold a system-required lock until we exit.
Add-Type -Namespace Win32 -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
$ES_CONTINUOUS = [uint32]'0x80000000'; $ES_SYSTEM_REQUIRED = [uint32]'0x00000001'
[Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED) | Out-Null

# Windows PowerShell pipes text to native programs as ASCII by default, turning any non-ASCII
# character in the prompt into '?'. Use UTF-8 both ways.
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$code = 1
try {
    "=== Daily crew shift started $(Get-Date -Format s) ($decision) ===" | Out-File -Append -Encoding utf8 $log
    # The prompt goes in on stdin: passed as an argument through claude.cmd, cmd.exe mangles its quotes.
    $prompt | & $claude -p --permission-mode dontAsk --allowedTools $allowed --max-turns $MaxTurns --output-format text 2>&1 |
        ForEach-Object { Hide-Secrets "$_" } |
        Out-File -Append -Encoding utf8 $log
    $code = $LASTEXITCODE
} finally {
    "=== Finished $(Get-Date -Format s) with exit code $code ===" | Out-File -Append -Encoding utf8 $log
    [Win32.Power]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
}
exit $code
