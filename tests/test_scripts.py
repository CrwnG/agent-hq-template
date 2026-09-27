"""Guards for the daily-shift hardening. Each assertion is a lesson learned the hard way;
if you change the scripts, keep these true (or change the test on purpose)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CREW = (SCRIPTS / "daily_crew.ps1").read_text(encoding="utf-8")
INSTALL = (SCRIPTS / "install_schedule.ps1").read_text(encoding="utf-8")
CONFIG = (SCRIPTS / "crew.config.ps1").read_text(encoding="utf-8")


def test_prompt_goes_in_on_stdin():
    assert "$prompt | & $claude -p" in CREW


def test_dontask_with_allowlist():
    assert "--permission-mode dontAsk" in CREW and "--allowedTools $allowed" in CREW


def test_never_bills_the_api():
    assert "Remove-Item Env:ANTHROPIC_API_KEY" in CREW


def test_secrets_masked_in_log():
    assert "Hide-Secrets" in CREW and "sk-ant-" in CREW and ".env" in CREW


def test_wake_lock_held_and_released():
    assert CREW.count("SetThreadExecutionState(") >= 3  # declare, acquire, release
    assert "finally" in CREW


def test_markers_and_resume_note():
    for marker in ("=== Daily crew shift started", "=== Finished", "=== Claimed by interactive session",
                   "an earlier shift today was interrupted"):
        assert marker in CREW, marker
    assert "=== Claimed by interactive session" in (SCRIPTS / "claim_day.ps1").read_text(encoding="utf-8")


def test_daily_and_logon_catch_up_triggers():
    assert "New-ScheduledTaskTrigger -Daily -At $RunTime" in INSTALL
    assert "-AtLogOn" in INSTALL and "$logonCatchUp.Delay" in INSTALL
    assert "StartWhenAvailable" in INSTALL and "IgnoreNew" in INSTALL


def test_config_at_top():
    for name in ("$ProjectName", "$RunTime", "$LogonDelayMinutes", "$MaxTurns", "$HqPort"):
        assert name in CONFIG
    for script in (CREW, INSTALL):
        assert ". (Join-Path $PSScriptRoot 'crew.config.ps1')" in script


POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


@pytest.mark.skipif(sys.platform != "win32" or not POWERSHELL, reason="Windows PowerShell only")
@pytest.mark.parametrize("logs,now,expected", [
    ({}, "2026-03-10 09:00", "skip: too early"),                                      # first install
    ({}, "2026-03-10 13:00", "run: scheduled shift"),
    ({"2026-03-09": "started\nfinished0"}, "2026-03-10 09:00", "skip: too early"),    # normal morning
    ({"2026-03-09": "started\nfinished0"}, "2026-03-10 12:40", "run: scheduled shift"),
    ({"2026-03-08": "started\nfinished0"}, "2026-03-10 08:15", "run: catching up a missed day"),
    ({"2026-03-09": "started\nfinished1"}, "2026-03-10 08:15", "run: catching up a missed day"),
    ({"2026-03-09": "claimed"}, "2026-03-10 09:00", "skip: too early"),               # claimed = done
    ({"2026-03-10": "claimed"}, "2026-03-10 13:00", "skip: claimed"),
    ({"2026-03-10": "started\nfinished0"}, "2026-03-10 13:00", "skip: today's shift already finished"),
    ({"2026-03-10": "started"}, "2026-03-10 13:00", "(resuming an interrupted shift)"),
])
def test_daily_crew_decisions(tmp_path, logs, now, expected):
    lines = {"started": "=== Daily crew shift started x ===",
             "finished0": "=== Finished x with exit code 0 ===",
             "finished1": "=== Finished x with exit code 1 ===",
             "claimed": "=== Claimed by interactive session x ==="}
    for day, body in logs.items():
        text = "\n".join(lines[k] for k in body.split("\n")) + "\n"
        (tmp_path / f"daily-{day}.log").write_text(text, encoding="utf-8-sig")  # BOM, like PowerShell
    r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(SCRIPTS / "daily_crew.ps1"), "-DryRun", "-LogDir", str(tmp_path), "-Now", now],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert expected in r.stdout, r.stdout
