# ---------------------------------------------------------------------------------------------
#  Crew schedule settings: the ONE place to edit. Dot-sourced by daily_crew.ps1,
#  install_schedule.ps1, uninstall_schedule.ps1 and claim_day.ps1.
#  After changing anything here, re-run scripts\install_schedule.ps1.
# ---------------------------------------------------------------------------------------------

# Names the scheduled tasks "<ProjectName>-DailyCrew" and "<ProjectName>-HQ". Letters, digits, '-' only.
$ProjectName = 'AgentHQ'

# Daily shift start, 24-hour local time. Pick a time the machine is usually on and you're not
# using it heavily (a laptop that is off at night should NOT use 03:00).
$RunTime = '12:30'

# The logon catch-up trigger fires this many minutes after you log on (gives the network,
# sync clients and your own startup a moment first).
$LogonDelayMinutes = 10

# On a normal day (yesterday's shift finished) a logon catch-up only starts the shift if it is
# later than RunTime minus this many minutes; earlier than that, the daily trigger will run it.
$LogonGraceMinutes = 5

# Hard stop for a shift (Task Scheduler kills it after this long).
$ShiftHours = 4

# Claude Code turn budget for one shift.
$MaxTurns = 200

# Dashboard port (the HQ task starts it at logon).
$HqPort = 8787

# Wake the machine from sleep for the daily trigger. Off by default: many laptops
# shouldn't wake in a bag. The shift holds its own wake lock once it has started.
$WakeToRun = $false

# Extra tools the unattended shift may use, on top of the base allowlist in daily_crew.ps1.
# Keep this tight: anything not listed is refused (dontAsk mode), never prompted.
# Examples: 'Bash(ffmpeg *)', 'Bash(npm test*)', 'Bash(.venv/Scripts/python.exe scripts/*)'
$ExtraAllowedTools = @()
